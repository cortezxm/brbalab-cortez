"""
Unified Rating Processor for Sports Leagues

This module implements a flexible framework for calculating, updating, and simulating team ratings
for sports leagues (e.g., EPL, FIFA) using statistical models such as the Kalman filter and probabilistic simulations.
League-specific parameters are managed via the LeagueParameters class, allowing easy adaptation to different competitions.

Main components:
    - LeagueParameters: Centralizes configuration for each league (initial ratings, uncertainty, home advantage, etc.).
    - RatingProcessor: Provides methods for rating updates, match outcome probabilities, and season simulations.

Key features:
    - Kalman filter-based rating updates for each match.
    - Probabilistic simulation of league outcomes (champion, top 4, relegation).
    - Support for multiple leagues via configuration.
    - Utility methods for probability calculations and quadrature integration.

Typical usage:
    params = LeagueParameters('EPL')  # or 'FIFA'
    processor = RatingProcessor(params)
    df = pd.read_csv("data_files/EPLGames2024.csv")
    df = processor.update_ratings(df)
    standings = processor.simulate(standings_df, games_df)
"""

import numpy as np
import math
import pandas as pd
import random
import copy
from abc import ABC, abstractmethod

# Reference date for the season simulation. None means the real current date;
# set it (e.g. "2025-09-09") to replay the season as it looked on that day.
TODAY = None


class LeagueParameters:
    """
    Stores and manages configuration parameters for a sports league.

    This class centralizes all league-specific values required for rating calculations,
    such as initial ratings, uncertainty, home field advantage, and draw frequency.
    It allows easy extension to new leagues by updating the LEAGUE_CONFIG dictionary.

    Attributes:
        default_rating (float): Initial rating assigned to teams in the league.
        default_stddev (float): Initial standard deviation of team skills.
        epsilon (float): Variance inflation parameter; controls uncertainty growth per time unit.
        number_of_simulations (int): Number of simulations to run for probabilistic predictions.
        eta (float): Home field advantage parameter.
        s (int): Scale factor to normalize rating differences.
        k (float): Draw/tie parameter in ternary outcome models; higher values imply more draws.
        draw_frequency (float): Empirical draw rate for the league.
        N (int): Number of matches to consider for initial ratings.

    Methods:
        __init__(league): Initializes parameters for the specified league.
    """
    
    LEAGUE_CONFIG = {
        'EPL': {
            'DEFAULT_RATING': 1000.0,    # Default rating for EPL teams
            'DEFAULT_STDDEV': 120.0,     # Initial stddev (S * 0.2)
            'EPSILON': 0.036,            # Variance inflation (S^2 * 0.0000001)
            'NUMBER_OF_SIMULATIONS': 1000,  # Simulations for predictions
            'ETA': 0.1,                  # Home field advantage
            'S': 600,                    # Scale factor
            'K': 0.67,                   # Draw/tie parameter
            'DRAW_FREQUENCY': 0.242,     # Empirical draw rate
            'N': 25                      # Number of matches to consider for initial ratings
        },
        'FIFA': {
            'DEFAULT_RATING': 1000.0,
            'DEFAULT_STDDEV': 600.0,       # Initial stddev (S * 1)
            'EPSILON': 3.6,              # Variance inflation (S^2 * 0.00001)
            'NUMBER_OF_SIMULATIONS': 1000,
            'ETA': 0.3,
            'S': 600,
            'K': 0.67,
            'DRAW_FREQUENCY': 0.229,
            'N': 25                     
        }
    }

    def __init__(self, league):
        """
        Initialize league parameters for the specified league.

        Args:
            league (str): League identifier (e.g., 'EPL', 'FIFA').

        Raises:
            ValueError: If the league is not supported.
        """
        if league not in self.LEAGUE_CONFIG:
            raise ValueError(f"Unsupported league type. Valid leagues: {list(self.LEAGUE_CONFIG.keys())}")
        config = self.LEAGUE_CONFIG[league]
        # Store league parameters in attributes
        self.default_rating = config['DEFAULT_RATING']
        self.default_stddev = config['DEFAULT_STDDEV']
        self.epsilon = config['EPSILON']
        self.number_of_simulations = config['NUMBER_OF_SIMULATIONS']
        self.eta = config['ETA']
        self.s = config['S']
        self.k = config['K']
        self.draw_frequency = config['DRAW_FREQUENCY']
        self.N = config['N']
        
EPL_PARAMS = LeagueParameters('EPL')
FIFA_PARAMS = LeagueParameters('FIFA')


class RatingProcessor(ABC):
    """
    General processor for team ratings and probabilistic simulations in supported sports leagues.

    This class provides unified methods for:
        - Updating team ratings after each match using a Kalman filter-based approach.
        - Calculating match outcome probabilities (win/draw/loss) based on current ratings.
        - Simulating the remainder of a season to estimate probabilities for champion, top 4, and relegation.
        - Supporting multiple leagues via the LeagueParameters configuration.

    Attributes:
        league_params (LeagueParameters): Object containing league-specific parameters.

    Methods:
        __init__(league_params): Initializes the processor with league parameters.
        update_ratings(df): Updates ratings for all matches in the DataFrame.
        _get_previous_rating(df, date, team_name): Retrieves previous rating and stddev for a team.
        _find_day_difference(id_, df): Calculates days since last match for a team.
        update_rating_kalman(...): Updates ratings using the Kalman filter approach.
        getOdds(...): Calculates match outcome probabilities based on ratings.
        Pr_Home(...), Pr_Away(...), Pr_Draw(...): Helper methods for probability calculations.
        percentage(a, b): Converts a ratio to a percentage.
        simulate(standings, games): Simulates the rest of the season and updates standings with probabilities.
        get_current_week(games): Returns the current week based on played games.
        get_possibilities(...): Calculates probabilities for a match given ratings and rest days.
        get_miu(...): Calculates rating difference between teams.
        get_sigma(...): Calculates combined uncertainty for a match.
        Gauss_Hermite_quadrature(n): Returns nodes and weights for Hermite quadrature.
        get_probabilities(teams, number_of_simulations): Aggregates simulation results into probabilities.
    """
    def __init__(self, league_params: LeagueParameters):
        """
        Initialize the rating processor with league-specific parameters.

        Args:
            league_params (LeagueParameters): Parameters for the league.
        """
        self.league_params = league_params
        
    def update_ratings(self, df):       
        """
        Updates team ratings for all matches in the DataFrame using a Kalman filter approach.

        Iterates over each match, retrieves previous ratings and uncertainties, applies the Kalman filter update,
        calculates win/draw/loss probabilities, and stores the updated values in the DataFrame.

        Args:
            df (pd.DataFrame): DataFrame containing match data.

        Returns:
            pd.DataFrame: DataFrame with updated ratings, uncertainties, and probabilities for each match.
        """
        print(f"Updating ratings")
        
        # Create columns for rating calculations, we initialize them with default values
        df['home_rating'] = self.league_params.default_rating
        df['away_rating'] = self.league_params.default_rating
        df['home_stddev'] = self.league_params.default_stddev
        df['away_stddev'] = self.league_params.default_stddev
        
        # Convert the 'date' column to datetime format for proper comparison
        df['date'] = pd.to_datetime(df['date'])
        
        # Iterate through each match in the DataFrame
        for index, row in df.iterrows():
            id_ = row['id']
            date = row['date']
            home_team = row['home_team']
            away_team = row['away_team']
            home_score = row['home_score']
            away_score = row['away_score']

            # Get previous ratings and stddevs
            previous_rating_home, previous_stddev_home = self._get_previous_rating(df, date, home_team)
            previous_rating_away, previous_stddev_away = self._get_previous_rating(df, date, away_team)
            
            # Get home field advantage parameter
            try:
                if row['neutral_pitch']:
                    eta = 0
                else:
                    eta = self.league_params.eta
            except KeyError:
                eta = self.league_params.eta
            
            # Determine the match outcome
            y_t = 1
            if home_score > away_score:
                y_t = 2
            elif away_score > home_score:
                y_t = 0
                
            # Calculate the number of days since the last match
            num_days = self._find_day_difference(id_, df)
            
            # Update ratings using Kalman filter
            # This will return a dictionary with the new ratings and stddevs
            kalmanRatings = self.update_rating_kalman(
                num_days,
                previous_rating_home,
                previous_stddev_home,
                previous_rating_away,
                previous_stddev_away,
                y_t,
                eta
            )

            # Calculate win/draw/loss probabilities based on updated ratings
            probabilities, _ = self.getOdds(previous_rating_home, previous_rating_away, eta)
            # Extract probabilities for home win, draw, and away win
            Pr_HomeWin = probabilities['Pr_H3']
            Pr_Draw = probabilities['Pr_D3']
            Pr_AwayWin = probabilities['Pr_A3']
            
            # Extract new ratings and stddevs from kalmanRatings
            newRatingHome = kalmanRatings['newRatingHome']
            newRatingAway = kalmanRatings['newRatingAway']
            newstddevHome = kalmanRatings['newstddevHome']
            newstddevAway = kalmanRatings['newstddevAway']
            
            # Calculate rating changes
            ratingChangeHome = newRatingHome - previous_rating_home
            ratingChangeAway = newRatingAway - previous_rating_away
            
            # Update the DataFrame with new ratings, stddevs, and probabilities
            df.at[index, 'home_rating'] = newRatingHome
            df.at[index, 'away_rating'] = newRatingAway
            df.at[index, 'home_stddev'] = newstddevHome
            df.at[index, 'away_stddev'] = newstddevAway
            df.at[index, 'Pr_HomeWin'] = Pr_HomeWin
            df.at[index, 'Pr_Draw'] = Pr_Draw
            df.at[index, 'Pr_AwayWin'] = Pr_AwayWin
            df.at[index, 'ratingChangeHome'] = ratingChangeHome
            df.at[index, 'ratingChangeAway'] = ratingChangeAway
        
        return df
        
    def _get_previous_rating(self, df, date, team_name):
        """
        Retrieves the previous rating and standard deviation for a team before a given date.

        Args:
            df (pd.DataFrame): DataFrame containing match data.
            date (str or pd.Timestamp): Date of the current match.
            team_name (str): Name of the team.

        Returns:
            tuple: (previous_rating, previous_stddev)
        """
        # Get the games of the team before the input date
        team_games = df[((df['date'] < pd.to_datetime(date)) & ((df['home_team'] == team_name) | (df['away_team'] == team_name)))]
        
        # If the team has not played any games before the input date, return the default rating and stddev
        if team_games.empty:
            return self.league_params.default_rating, self.league_params.default_stddev

        # Get the last game of the team before the input date
        last_game = team_games.iloc[-1]
        
        # Return the team's rating and stddev from the last game
        if last_game['home_team'] == team_name:
            return last_game['home_rating'], last_game['home_stddev']
        else:
            return last_game['away_rating'], last_game['away_stddev']
        
    def _find_day_difference(self, id_, df):
        """
        Calculates the number of days since the last match for a team.

        Args:
            id_ (str): Unique identifier for the current match.
            df (pd.DataFrame): DataFrame containing match data.

        Returns:
            int: Number of days since the team's last match, or 0 if no previous match.
        """
        # Extract the date of the match
        match_date = df.loc[df['id'] == id_, 'date'].values[0]
        
        # Get the last game date
        # Filter home and away scores to ensure we only consider completed games (home_score != -1 and away_score != -1)
        last_game_date = df.loc[(df['date'] < match_date) & (df['home_score'] != -1) & (df['away_score'] != -1), 'date'].max()
        
        # Calculate the difference in days, if there is no last game, return 0
        return (match_date - last_game_date).days if pd.notna(last_game_date) else 0
    
    def update_rating_kalman(self, days, hr, hs, ar, as_, y_t, eta):
        """
        Updates the ratings and uncertainties of two teams using the Simplified Kalman Filter (vSKF).

        This implementation follows the one-fits-all rating framework (Szczecinski & Tihon, 2023).
        It models team skills as Gaussians and updates their means and variances based on match outcomes.

        Args:
            days (int): Number of days since the last match (used for variance inflation).
            hr (float): Home team's prior rating (mean of skill distribution).
            hs (float): Home team's prior standard deviation.
            ar (float): Away team's prior rating.
            as_ (float): Away team's prior standard deviation.
            y_t (int): Match outcome (2 = home win, 1 = draw, 0 = away win).
            eta (float): Home field advantage parameter.

        Returns:
            dict: A dictionary with updated ratings and standard deviations:
                - 'newRatingHome': Updated mean rating for the home team.
                - 'newRatingAway': Updated mean rating for the away team.
                - 'newstddevHome': Updated standard deviation for the home team.
                - 'newstddevAway': Updated standard deviation for the away team.
        """
        # Extract league parameters
        s = self.league_params.s                # Scale factor
        epsilon = self.league_params.epsilon    # Variance inflation
        k = self.league_params.k                # Draw/tie parameter

        # Initialize vectors for Kalman update
        mu = np.array([hr, ar])                 # vector of the skills: mu_{t-1}
        var = np.array([hs ** 2, as_ ** 2])     # diagonal vector of the uncertainties: diag(V_{t-1}), this is Bt^2.v(t-1) in Eq. (45)
                                                # As we take take Beta = 1, the first part of Eq. (45): β^2 * v_{t-1} is equal to v_{t-1}
        unit_vec = np.ones(len(mu))             # Unit Vector of 1's
        x_t = np.array([1, -1])                 # scheduling vector x_t
        
        # Calculate variables for Kalman update
        epsilon_t = days * epsilon              # Eq. (5)
        y_t_hat = y_t * 0.5                     # "Score" of the game, check Appendix D, after Eq. (129)
        z = np.dot(x_t.T, mu) / s + eta         # Difference of team´s habilities, add Home Field advantage, z  = (Bt.xT.mu)/s + eta

        # Kalman update equations
        var_bar = var + np.dot(epsilon_t, unit_vec) # Eq. (45)
        w_t = np.sum(var_bar)                       # Eq. (46)
        
        # Auxiliar equations for Eq. (47-48) of Kalman update
        g_dav = (np.power(10, z) + k / 2) / (np.power(10, (-1 * z)) + k + np.power(10, z)) # Eq. (131)
        g_t = -2 * math.log(10) * (y_t_hat - g_dav)                                        # Eq. (128), which corresponds to Eq. (47)
        h_t = np.power(math.log(10), 2) * (k * np.power(10, z) + 4 + k * np.power(10, (-1 * z))) / (
            np.power((np.power(10, z) + k + np.power(10, -1 * z)), 2))                     # Eq (129), whic correspongs to Eq. (48)
        dot_prod = x_t * (s * g_t) / (s**2 + h_t * w_t)                                    # Second part of the element-by-element multiplication in Eq. (49)
        newRatings = mu - np.multiply(var_bar, dot_prod)                                   # Eq. (49), new ratings refers to mu_t
        dot_prod = np.dot(np.absolute(x_t), (h_t / (np.power(s, 2) + np.dot(h_t, w_t))))   # Second part of the element-by-element multiplication in Eq. (50)
        newVariances = np.multiply(var_bar, 1 - np.multiply(var_bar, dot_prod))            # Eq. (50), new variances refers to V_t
        
        return {
            'newRatingHome': newRatings[0],
            'newRatingAway': newRatings[1],
            'newstddevHome': newVariances[0] ** 0.5,
            'newstddevAway': newVariances[1] ** 0.5
        }
        
    def getOdds(self, rating_home, rating_away, eta):
        """
        Calculate the probabilities for home win, draw, and away win based on team ratings.

        Args:
            rating_home (float): Rating of the home team.
            rating_away (float): Rating of the away team.
            eta (float): Home field advantage parameter.

        Returns:
            tuple: Two dictionaries:
                - {'Pr_H3': ..., 'Pr_D3': ..., 'Pr_A3': ...} (probabilities for 3-way outcomes)
                - {'Pr_H2': ..., 'Pr_A2': ...} (probabilities adjusted for draws)
        """
        
        # For win, draw, and loss probabilities, check appendix D, Eq. (127)
        drawParameter = (2 * self.league_params.draw_frequency) / (1 - self.league_params.draw_frequency)
        delta = rating_home - rating_away + eta * self.league_params.s
        # delta / s corresponds to z, and drawParameter is k in Eq. (127)
        Pr_H3 = self.Pr_Home(delta/self.league_params.s, drawParameter)
        Pr_A3 = self.Pr_Away(delta/self.league_params.s, drawParameter)
        Pr_D3 = self.Pr_Draw(delta/self.league_params.s, drawParameter)

        # Adjusted probabilities accounting for draw
        Pr_H2 = Pr_H3 + 0.5 * Pr_D3
        Pr_A2 = Pr_A3 + 0.5 * Pr_D3

        return {'Pr_H3': Pr_H3, 'Pr_D3': Pr_D3, 'Pr_A3': Pr_A3}, {'Pr_H2': Pr_H2, 'Pr_A2': Pr_A2}
    
    def Pr_Home(self, z, k):
        """
        Calculate the probability of a home win given z and draw parameter.

        Args:
            z (float): Normalized rating difference.
            k (float): Draw parameter.

        Returns:
            float: Probability of home win (percentage).
        """
        
        # (10^z) / (10^z + 10^(-z) + k)
        num = np.power(10, z)
        denom = np.power(10, z) + np.power(10, -z) + k
        return self.percentage(num, denom)
    
    def Pr_Away(self, z, k):    
        """
        Calculate the probability of an away win given z and draw parameter.

        Args:
            z (float): Normalized rating difference.
            k (float): Draw parameter.

        Returns:
            float: Probability of away win (percentage).
        """
        
        # (10^-z) / (10^z + 10^(-z) + k)
        num = np.power(10, -z)
        denom = np.power(10, z) + np.power(10, -z) + k
        return self.percentage(num, denom)
    
    def Pr_Draw(self, z, k):
        """
        Calculate the probability of a draw given z and draw parameter.

        Args:
            z (float): Normalized rating difference.
            k (float): Draw parameter.

        Returns:
            float: Probability of draw (percentage).
        """
        
        # (k) / (10^z + 10^(-z) + k)
        num = k
        denom = np.power(10, z) + np.power(10, -z) + k
        return self.percentage(num, denom)

    def percentage(self, a, b):
        """
        Utility function to convert a ratio to a percentage.

        Args:
            a (float): Numerator.
            b (float): Denominator.

        Returns:
            float: Percentage value.
        """
        return (a / b * 100)
    
    def simulate(self, standings, games):
        """
        Simulates the remainder of the season to estimate probabilities for champion, top 4, and relegation.

        Runs multiple probabilistic simulations of future matches, updates team points, and aggregates
        the frequency of each team finishing in key positions.

        Args:
            standings (pd.DataFrame): DataFrame with current league standings.
            games (pd.DataFrame): DataFrame with all scheduled matches.

        Returns:
            pd.DataFrame: Standings DataFrame updated with probability columns.
        """
        
        # Identify the current week based on played games
        current_week = int(self.get_current_week(games))
        today = pd.Timestamp(TODAY or 'today').normalize() # Normalize to remove time component
        df_current_week = standings[standings['week'] == current_week] # Get teams in the current week
        
        # Initialize teams dictionary with current ratings and points
        teams = {
            row['team']: {
                'points': row['points'],
                'rating': row['rating'],
                'stddev': row['stddev'],
                'last_game_date': None,
                'rank': {j: 0 for j in range(1, 21)},
                'probability': {}
            }
            for _, row in df_current_week.iterrows()
        }
        
        # Determine the last game date for each team
        # Convert 'date' column to datetime
        games['date'] = pd.to_datetime(games['date'], errors='coerce')
        future_games_df = games[games['date'] > today]
        
        for team in teams:
            # Find the last game date for the team
            last_dates = future_games_df[
                (future_games_df['home_team'] == team) | (future_games_df['away_team'] == team)
            ]['date']
            teams[team]['last_game_date'] = last_dates.min() if not last_dates.empty else None
        
        # Prepare list of future games
        future_games = future_games_df[['home_team', 'away_team', 'date']].drop_duplicates()
        future_games = future_games.sort_values('date').values.tolist()
        # Create a dictionary to store precomputed game possibilities
        game_possibilities = {}
        for game in future_games:
            home_team, away_team, game_day = game
            home_day = teams[home_team]['last_game_date']
            away_day = teams[away_team]['last_game_date']
            home_days = (game_day - home_day).days if home_day else None
            away_days = (game_day - away_day).days if away_day else None

            # Precompute and store the match outcome probabilities
            game_possibilities[tuple(game)] = self.get_possibilities(
                teams[home_team]['rating'], teams[away_team]['rating'],
                teams[home_team]['stddev'], teams[away_team]['stddev'],
                home_days, away_days
            )
                    
        for _ in range(self.league_params.number_of_simulations):
            # print(_) # Uncomment to see progress of simulations
            # Deep copy the teams dictionary to avoid modifying the original during simulation
            teams_copy = copy.deepcopy(teams)

            for game in future_games:
                # Retrieve precomputed probabilities
                results = game_possibilities[tuple(game)]

                arr = ['home_win', 'draw', 'away_win']
                # Choose outcome based on probabilities
                result = np.random.choice(arr, p=[results[0], results[1], results[2]])

                # Update points based on simulated match result
                if result == arr[0]:
                    teams_copy[game[0]]['points'] += 3
                elif result == arr[1]:
                    teams_copy[game[0]]['points'] += 1
                    teams_copy[game[1]]['points'] += 1
                else:
                    teams_copy[game[1]]['points'] += 3

            # Randomly assign rank to the teams with same rank
            team_points = [[team_name, info['points']] for team_name, info in teams_copy.items()]
            sorted_teams = sorted(team_points, key=lambda x: (-x[1], random.random()))

            # Update rank counts based on simulation results
            for idx, (team_name, points) in enumerate(sorted_teams):
                current_rank = idx + 1
                teams[team_name]['rank'][current_rank] += 1
                
        # Calculate probabilities based on simulation results
        teams = self.get_probabilities(teams, self.league_params.number_of_simulations)
        
        # Update standings DataFrame with calculated probabilities        
        for index, stand in standings.iterrows():
            if standings.loc[index, 'week'] == current_week:
                t_name = stand['team']
                standings.loc[index, 'champion'] = teams[t_name]['probability']["1st"]
                standings.loc[index, "champions_league"] = teams[t_name]['probability']["top4"]
                standings.loc[index, "relegation_to_EFL"] = teams[t_name]['probability']["bottom3"]
                
        return standings
            
    def get_current_week(self, games):
        """
        Returns the current week of the season based on the latest played games.

        Filters the games DataFrame to include only matches that have been played (scores not -1),
        and returns the maximum week number found.

        Args:
            games (pd.DataFrame): DataFrame containing all scheduled matches.

        Returns:
            int or None: The current week number, or None if no games have been played.
        """
        
        # Filter games that have been played (home_score and away_score are not -1)
        valid_games = games[(games['home_score'] != -1) & (games['away_score'] != -1)]
        if not valid_games.empty:
            # Return the maximum week number from the valid games
            return valid_games['gameweek'].max()
        return None
    
    def get_possibilities(self, home_rating, away_rating, home_stddev, away_stddev, home_days, away_days):
        """
        Calculates the probabilities of match outcomes (home win, draw, away win) based on team ratings,
        uncertainties, and days since last match using Gauss-Hermite quadrature.

        Args:
            home_rating (float): Rating of the home team.
            away_rating (float): Rating of the away team.
            home_stddev (float): Standard deviation of the home team's rating.
            away_stddev (float): Standard deviation of the away team's rating.
            home_days (int): Days since the last match for the home team.
            away_days (int): Days since the last match for the away team.

        Returns:
            tuple: Probabilities for home win, away win, and draw.
        """
        miu = self.get_miu(home_rating, away_rating) + self.league_params.eta
        sigma = self.get_sigma(home_days, away_days, home_stddev, away_stddev)
        r_w = self.Gauss_Hermite_quadrature(self.league_params.N)
        draw_param = (2 * self.league_params.draw_frequency) / (1 - self.league_params.draw_frequency)
        
        x_vals = np.sqrt(2) * np.array(r_w[0]) * sigma + miu
        exp = (x_vals / (2 * self.league_params.s))
        # Divide by 100 to convert from percentage to probability
        home_probs = self.Pr_Home(exp, draw_param) / 100
        away_probs = self.Pr_Away(exp, draw_param) / 100
        draw_probs = self.Pr_Draw(exp, draw_param) / 100
        
        home_win = (1 / np.sqrt(np.pi)) * np.sum(np.array(r_w[1]) * home_probs)
        away_win = (1 / np.sqrt(np.pi)) * np.sum(np.array(r_w[1]) * away_probs)
        draw = (1 / np.sqrt(np.pi)) * np.sum(np.array(r_w[1]) * draw_probs)
        return home_win, away_win, draw

    def get_miu(self, home_rating, away_rating):
        """
        Calculates the difference in ratings between home and away teams.

        Args:
            home_rating (float): Rating of the home team.
            away_rating (float): Rating of the away team.

        Returns:
            float: Difference in ratings (miu).
        """
        x_t_prime = np.array([1, -1])
        v_t = np.array([home_rating, away_rating])
        return np.dot(x_t_prime.T, v_t)
    
    def get_sigma(self, home_days, away_days, home_stddev, away_stddev):
        """
        Calculates the combined standard deviation for home and away teams, accounting for days since last match.

        Args:
            home_days (int): Days since the last match for the home team.
            away_days (int): Days since the last match for the away team.
            home_stddev (float): Standard deviation of the home team's rating.
            away_stddev (float): Standard deviation of the away team's rating.

        Returns:
            float: Combined standard deviation (sigma).
        """
        # Calculate sigma_t_prime squared
        v_t = np.square([home_stddev, away_stddev])
        sigma_t_prime_squared = v_t.sum() + self.league_params.epsilon * (home_days + away_days)

        # Return the square root of sigma_t_prime squared to get sigma_t_prime
        return np.sqrt(sigma_t_prime_squared)
    
    def Gauss_Hermite_quadrature(self, n):
        """
        Returns nodes and weights for Gauss-Hermite quadrature of order n.

        Used for numerical integration in probability calculations.

        Args:
            n (int): Number of quadrature points.

        Returns:
            tuple: (nodes, weights) for Hermite quadrature.
        """
        r_w = np.polynomial.hermite.hermgauss(n)
        return r_w
    
    def get_probabilities(self, teams, number_of_simulations):
        """
        Aggregates simulation results into probabilities for each team.

        Calculates the percentage of times each team finishes first, in the top 4, or in the bottom 3
        across all simulations.

        Args:
            teams (dict): Dictionary of teams with rank counts.
            number_of_simulations (int): Number of simulations performed.

        Returns:
            dict: Updated teams dictionary with probability fields.
        """
        for team_name, data in teams.items():
            first_place_prob = round((data['rank'][1] / number_of_simulations) * 100)
            top_4_prob = round(sum(data['rank'][i] for i in range(1, 5)) / number_of_simulations * 100)
            bottom_3_prob = round(sum(data['rank'][i] for i in range(18, 21)) / number_of_simulations * 100)

            data['probability'] = {
                '1st': first_place_prob,
                'top4': top_4_prob,
                'bottom3': bottom_3_prob
            }

        return teams
    
# Example usage:
if __name__ == "__main__":
    # Test for EPL
    # epl_processor = RatingProcessor(EPL_PARAMS)
    # Test para actualizar ratings
    # df = pd.read_csv("EPL_data_files/EPLGames2025_NewScrapping.csv")
    # print(df.head())
    # epl_processor.update_ratings(df, "EPL_data_files/EPLGames2025_NewScrapping.csv")
    
    # Test for the simulation
    # games = pd.read_csv("EPL_data_files/EPLGames2025_NewScrapping.csv")
    # standings = pd.read_csv("EPL_data_files/EPLStandings2025_NewScrapping.csv")
    # new_standings = epl_processor.simulate(standings, games)
    # new_standings.to_csv("EPL_data_files/EPLStandings2025_NewScrapping.csv", index=False)
    
    # Test for FIFA
    fifa_processor = RatingProcessor(FIFA_PARAMS)
    df_fifa = pd.read_csv("FIFA_data_files/AllGames.csv")
    ratings = fifa_processor.update_ratings(df_fifa)
    ratings.to_csv("FIFA_data_files/FIFAGames2025.csv", index=False)
