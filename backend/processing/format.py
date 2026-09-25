"""
Formatting and Visualization Utilities for Sports League Data

This module provides tools for generating weekly standings, team statistics, and visualizations
for various sports leagues (e.g., EPL, FIFA). It includes methods for building standings tables,
mapping team names to abbreviations, generating HTML snippets for logos, and creating rating evolution plots.

Main components:
    - BaseFormat: Main class for formatting league data, generating standings, and producing visual elements.
    - getStandings: Builds a weekly standings DataFrame with team stats, rankings, and HTML logos.
    - get_fifa_graphs: Generates rating evolution plots for FIFA continental confederations.
    - get_team_stats: Computes per-team statistics (wins, draws, losses, points, ratings, etc.) for a given week.

Key features:
    - Weekly standings generation with dynamic ranking and HTML logo formatting.
    - Flexible mapping of team names to 3-letter abbreviations for multiple leagues.
    - Visualization of rating evolution for top and dispersed teams by confederation.
    - Designed for extensibility to other leagues and competitions.

Typical usage:
    epl_format = BaseFormat(epl_df, 2025, team_abbr_EPL)
    standings = epl_format.getStandings()
    fifa_format = BaseFormat(fifa_df, 2025, team_abbr_FIFA)
    fifa_format.get_fifa_graphs()
"""

import numpy as np
import math
import pandas as pd
import locale
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import matplotlib.dates as mdates
from abc import ABC, abstractmethod
from .team_dicts import team_abbr_EPL, team_abbr_FIFA   # Quit the '.' if running this file directly fot testing
from datetime import datetime


class BaseFormat(ABC):
    """
    Provides formatting, standings generation, and visualization utilities for sports league data.

    This class centralizes methods for:
        - Building weekly standings tables with team statistics.
        - Mapping team names to abbreviations and generating HTML logo snippets.
        - Creating rating evolution plots for FIFA confederations.
        - Computing per-team statistics (wins, draws, losses, points, ratings, etc.) for a given week.

    Attributes:
        df (pd.DataFrame): DataFrame containing match data for the league.
        year (int): Season year.
        team_abbr_dict (dict): Mapping from team names to 3-letter abbreviations.

    Methods:
        getStandings(): Generates a standings DataFrame for each week, including stats and HTML logos.
        get_fifa_graphs(): Creates and saves rating evolution plots for FIFA confederations.
        get_team_stats(week_games, team): Computes statistics for a team up to a given week.
    """
    def __init__(self, df, year, team_abbr_dict):
        self.df = df                            # DataFrame with the games
        self.year = year                        # Season year
        self.team_abbr_dict = team_abbr_dict    # Dict with team name to 3-letter abbreviation mapping
        
    def getStandings(self):
        """
        Generates the standings table for each week of the season.

        For each week, calculates team statistics (wins, draws, losses, points, rating, etc.)
        using all games up to and including the current week. Adds team abbreviations, logo HTML,
        and record strings. Sorts the standings by week, points, and wins, and assigns league ranking.

        Returns:
            pd.DataFrame: Standings DataFrame with statistics, abbreviations, logos, and rankings for each team and week.
        """
        games = self.df
        weeks = np.sort(games['gameweek'].unique())                             # All unique weeks in ascending order
        teams = pd.unique(games[['home_team', 'away_team']].values.ravel('K'))  # All unique teams

        frames = [] # List to hold DataFrames for each week's standings
        
        for week in weeks:
            week_games = games[games['gameweek'] <= week]                 # Games up to and including the current week
            week_stats = [
                {**self.get_team_stats(week_games, team), 'week': week}   # Get stats for each team
                for team in teams
            ]
            frames.append(pd.DataFrame(week_stats))                       # Create DataFrame for the week's standings and add to list 'frames'
        
        standings = pd.concat(frames, ignore_index=True)                                # Concatenate all weekly DataFrames into a single DataFrame 
        standings.insert(0, 'team_abbr', standings['team'].map(self.team_abbr_dict))    # Map team names to abbreviations and insert as first column of the standings DataFrame
        
        games.insert(5, 'away_abbr', games['away_team'].map(self.team_abbr_dict))       # Map away team names to abbreviations and insert as 5th column of the games DataFrame
        games.insert(4, 'home_abbr', games['home_team'].map(self.team_abbr_dict))       # Map home team names to abbreviations and insert as 4th column of the games DataFrame
        games['result'] = np.where(                                                     
            (games['home_score'] == -1) & (games['away_score'] == -1),                  # If scores are -1 (indicating unplayed), set result to '- / -'
            '- / -',
            games['home_score'].astype(str) + ' - ' + games['away_score'].astype(str)   # Otherwise, format result as 'home_score - away_score'
        )
        
        standings['week'] = standings['week'].astype(int)                       # Ensure 'week' column is of integer type
        standings.sort_values(by=['week', 'points', 'wins'], ascending=[False, False, False], inplace=True)
        standings.reset_index(drop=True, inplace=True)                          # Sort standings by week, points, and wins in descending order and reset index
        standings['league_rating'] = standings.groupby('week')\
            .cumcount() + 1                                                     # Assign league ranking within each week based on sorted order  

        # Insert the logo HTML and record columns in the standings DataFrame
        standings['logo'] = (
            '<div style="display: flex; align-items: center;">'
            '<img src="https://brbalab.com/wp-content/uploads/2023/05/' + standings['team_abbr'] +
            '.png" alt="" width="50" height="50" style="margin-right: 20px;" />'
            '<span>' + standings['team'] + '</span></div>'
        )
        
        standings['record'] = standings['wins'].astype(str) + '-' + \
            standings['draws'].astype(str) + '-' + standings['losses'].astype(str)
                        
        # Insert the logo HTML and result columns in the games DataFrame
        games['home_logo'] = (
            '<div style="display: flex; align-items: center;">'
            '<img src="https://brbalab.com/wp-content/uploads/2023/05/' + games['home_abbr'] +
            '.png" alt="" width="50" height="50" style="margin-right: 20px;" />'
            '<span>' + games['home_team'] + '</span></div>'
        )
                    
        games['away_logo'] = (
            '<div style="display: flex; align-items: center;">'
            '<img src="https://brbalab.com/wp-content/uploads/2023/05/' + games['away_abbr'] +
            '.png" alt="" width="50" height="50" style="margin-right: 20px;" />'
            '<span>' + games['away_team'] + '</span></div>'
        )
                    
        games['result'] = np.where(
            (games['home_score'] == -1) & (games['away_score'] == -1),
            '- / -',
            games['home_score'].astype(str) + ' - ' + games['away_score'].astype(str)
        )
        
        return standings # Return the final standings DataFrame
    
    def get_fifa_graphs(self):
        """
        Generates and saves rating evolution plots for FIFA continental confederations.

        For each confederation, creates two plots:
            - Top 5 teams by latest rating, showing their rating evolution over the last 3 years.
            - 5 dispersed teams across the rating spectrum, showing their rating evolution.

        Saves each plot as a PNG file in the 'FIFA_data_files/FIFA_graphs/' directory.
        """
        os.makedirs('FIFA_data_files/FIFA_graphs', exist_ok=True)
        CONTINENTAL_GROUPS = { # FIFA continental confederations and their member countries
            'UEFA': [
                'ALB', 'AND', 'ARM', 'AUT', 'AZE', 'BEL', 'BIH', 'BLR', 'BUL', 'CRO', 'CYP', 'CZE', 'DEN', 
                'ENG', 'ESP', 'EST', 'FRO', 'FIN', 'FRA', 'GEO', 'GER', 'GIB', 'GRE', 'HUN', 'ISL', 'IRL', 
                'ITA', 'KOS', 'KAZ', 'LVA', 'LIE', 'LTU', 'LUX', 'MLT', 'MDA', 'MNE', 'NED', 'NIR', 'NOR', 
                'POL', 'POR', 'ROU', 'RUS', 'SCO', 'SRB', 'SVK', 'SVN', 'SWE', 'SUI', 'TUR', 'UKR', 'WAL'
            ],
            'CAF': [
                'ALG', 'ANG', 'BEN', 'BOT', 'BFA', 'BDI', 'CMR', 'CPV', 'CTA', 'CHA', 'COM', 'CGO', 'COD', 
                'CIV', 'DJI', 'EGY', 'EQG', 'ERI', 'SWZ', 'ETH', 'GAB', 'GAM', 'GHA', 'GUI', 'GNB', 'KEN', 
                'LES', 'LBR', 'LBY', 'MAD', 'MWI', 'MLI', 'MTN', 'MRI', 'MAR', 'MOZ', 'NAM', 'NIG', 'NGA', 
                'RWA', 'STP', 'SEN', 'SEY', 'SLE', 'SOM', 'RSA', 'SSD', 'SDN', 'TAN', 'TOG', 'TUN', 'UGA', 
                'ZAM', 'ZIM'
            ],
            'AFC': [
                'AFG', 'BHR', 'BAN', 'BHU', 'BRU', 'CAM', 'CHN', 'TPE', 'PRK', 'KOR', 'HKG', 'IND', 'IDN', 
                'IRN', 'IRQ', 'ISR', 'JPN', 'JOR', 'KUW', 'KGZ', 'LAO', 'LIB', 'MAC', 'MAS', 'MDV', 'MNG', 
                'MYA', 'NEP', 'OMA', 'PAK', 'PLE', 'PHI', 'QAT', 'KSA', 'SIN', 'SRI', 'SYR', 'TJK', 'THA', 
                'TLS', 'TKM', 'UAE', 'UZB', 'VIE', 'YEM'
            ],
            'CONCACAF & CONMEBOL': [
                'AIA', 'ATG', 'BRB', 'BLZ', 'BER', 'CAN', 'CAY', 'CRC', 'CUB', 'CUW', 'DMA', 'DOM', 
                'SLV', 'GUA', 'GUY', 'HAI', 'HON', 'JAM', 'MEX', 'MSR', 'NCA', 'PAN', 'PUR', 'SKN', 
                'LCA', 'VIN', 'SUR', 'TRI', 'TCA', 'USA', 'VIR', 'ARG', 'BOL', 'BRA', 'CHI', 'COL', 
                'ECU', 'PAR', 'PER', 'URU', 'VEN'
            ],
            'OFC': [
                'ASA', 'AUS', 'COK', 'FIJ', 'NCL', 'NZL', 'PNG', 'SAM', 'SOL', 'TAH', 'TGA', 'VAN'
            ]
        }
        
        games = self.df
        games['date'] = pd.to_datetime(games['date'])           # Ensure 'date' column is in datetime format
        games = games.sort_values(by='date', ascending=False)   # Sort games by date in descending order
        
        # Get the lastest 3 years of data
        current_year = pd.Timestamp.now().year
        last_3_years = list(range(current_year - 2, current_year + 1))

        # Concatenate home and away ratings to get the latest rating per team
        home = games[['date', 'home_team', 'home_rating']].rename(columns={'home_team': 'team', 'home_rating': 'rating'})
        away = games[['date', 'away_team', 'away_rating']].rename(columns={'away_team': 'team', 'away_rating': 'rating'})
        ratings = pd.concat([home, away])

        # Order per date descending and keep the most recent per team
        latest_ratings = ratings.sort_values('date', ascending=False).drop_duplicates('team', keep='first')
        latest_ratings = latest_ratings.sort_values(by='rating', ascending=False).reset_index(drop=True)
        
        # Filter ratings to only include the last 3 years
        ratings = ratings[ratings['date'].dt.year.isin(last_3_years)]
        
        # Generate plots for each confederation
        for confederation_name, countries in CONTINENTAL_GROUPS.items():
            # Get the latest ratings for the confederation countries
            confederation = latest_ratings[latest_ratings['team'].isin(countries)].reset_index(drop=True)
            confederation['rank'] = confederation.index + 1 # Assign rank based on latest ratings
            
            # For the top 5 teams
            top_5 = list(zip(confederation.head(5)['team'], confederation.head(5)['rank'])) # List of tuples (team, rank)
            top_5_games = ratings[ratings['team'].isin([team for team, rank in top_5])].reset_index(drop=True) # Filter ratings for top 5 teams
            
            plt.figure(figsize=(12, 8)) # Create a new figure for the plot, change size as needed
            palette = sns.color_palette("Dark2", n_colors=len(top_5))  # Use a color palette with distinct colors for each team

            for team, rank in top_5:
                team_games = top_5_games[top_5_games['team'] == team]  # Filter ratings for the specific team
                sns.lineplot(   # Plot the rating evolution (lineplot) for the team
                    data=team_games, 
                    x='date', 
                    y='rating', 
                    label=f"{team} (#{rank})",
                    marker='o', 
                    markersize=8,
                    color=palette[rank-1]
                )

            plt.title(  # Title of the plot
                f'Top 5 teams for {confederation_name}',
                fontsize=22,
                fontweight='bold',
                fontname='DejaVu Sans'
            )
            
            # Axis labels and formatting
            plt.ylabel('Rating', fontsize=18, fontweight='bold', fontname='DejaVu Sans')
            plt.xticks(fontsize=14, fontname='DejaVu Sans')
            plt.yticks(fontsize=14, fontname='DejaVu Sans')
            plt.grid(True, linestyle='--', alpha=0.5) # Add grid lines for better readability

            # Date format: month and year
            try:
                locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
            except locale.Error:
                pass  # Month names fall back to the system locale
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
            plt.xticks(rotation=45) # Rotate x-axis labels 45 degrees for better readability
            
            plt.tight_layout() # Adjust layout to prevent clipping of labels

            # Leyend outside the plot
            plt.legend(
                title="Country and Position", 
                loc='center left', 
                bbox_to_anchor=(1, 0.5), 
                fontsize='large', 
                title_fontsize='large'
            )
            plt.gca().set_xlabel('') # Remove x-axis label
            # Important, adjust the dpi for better quality
            plt.savefig(f'FIFA_data_files/FIFA_graphs/top_5_teams_{confederation_name}_rating_evolution.png', bbox_inches='tight', dpi=300)
            plt.close()

            # Fot 5 dispersed teams
            difference = confederation['rating'].iloc[0] - confederation['rating'].iloc[-1] # Difference between highest and lowest rating
            step = difference / 5  # Step to get 5 evenly distributed ratings
            distributed_5 = []  # List to hold the 5 dispersed teams
            for i in range(6):
                value = confederation['rating'].iloc[-1] + i * step # Calculate the target rating value
                # Find the team with the closest rating to the target value
                closest_idx = (confederation['rating'] - value).abs().idxmin()
                closest_row = confederation.loc[closest_idx]
                distributed_5.append((closest_row['team'], closest_row['rank']))
            distributed_5 = distributed_5[::-1] # Reverse to have from highest to lowest
            distributed_5_games = ratings[ratings['team'].isin([team for team, rank in distributed_5])].reset_index(drop=True)
            plt.figure(figsize=(12, 8))
            palette = sns.color_palette("tab10", n_colors=len(distributed_5))

            for idx, (team, rank) in enumerate(distributed_5):
                team_games = distributed_5_games[distributed_5_games['team'] == team]
                sns.lineplot(
                    data=team_games, 
                    x='date', 
                    y='rating', 
                    label=f"{team} (#{rank})", 
                    marker='o', 
                    markersize=8,
                    color=palette[idx]
                )

            plt.title(
                f'Rating evolution for {confederation_name} teams',
                fontsize=22,
                fontweight='bold',
                fontname='DejaVu Sans'
            )
            plt.xlabel('Date', fontsize=18, fontweight='bold', fontname='DejaVu Sans')
            plt.ylabel('Rating', fontsize=18, fontweight='bold', fontname='DejaVu Sans')
            plt.xticks(fontsize=14, fontname='DejaVu Sans')
            plt.yticks(fontsize=14, fontname='DejaVu Sans')
            plt.grid(True, linestyle='--', alpha=0.5)

            try:
                locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
            except locale.Error:
                pass  # Month names fall back to the system locale
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
            plt.xticks(rotation=45)
            
            plt.tight_layout()

            plt.legend(
                title="Country and Position", 
                loc='center left', 
                bbox_to_anchor=(1, 0.5), 
                fontsize='large', 
                title_fontsize='large'
            )
            plt.gca().set_xlabel('')
            plt.savefig(f'FIFA_data_files/FIFA_graphs/dispersed_{confederation_name}_evolution.png', bbox_inches='tight', dpi=300)
            plt.close()

    def get_team_stats(self, week_games, team):
        """
        Computes statistics for a team up to a given week.

        Calculates wins, draws, losses, points, latest rating, rating change, and standard deviation
        for the specified team using only played games (scores not -1).

        Args:
            week_games (pd.DataFrame): DataFrame with all games up to the current week.
            team (str): Team name.

        Returns:
            dict: Dictionary with team statistics and placeholders for probabilities.
        """
        played_games = week_games[ # Filter to only include played games
            (week_games['home_score'] != -1) & (week_games['away_score'] != -1)
        ]
        # Filter games where the team is either home or away
        team_games = played_games[(played_games['home_team'] == team) | (played_games['away_team'] == team)]
        
        # Masks to identify home and away games for the team
        home_mask = team_games['home_team'] == team
        away_mask = team_games['away_team'] == team
        
        # Calculate wins, draws, losses, and points
        wins = ((home_mask & (team_games['home_score'] > team_games['away_score'])) |
            (away_mask & (team_games['away_score'] > team_games['home_score']))).sum()
        draws = ((team_games['home_score'] == team_games['away_score'])).sum()
        losses = ((home_mask & (team_games['home_score'] < team_games['away_score'])) |
                (away_mask & (team_games['away_score'] < team_games['home_score']))).sum()
        
        # Each win is 3 points, each draw is 1 point
        points = wins * 3 + draws
        
        if not team_games.empty:
            recent_game = team_games.loc[team_games.gameweek.idxmax()] # Most recent game played by the team
            # Get the latest rating, rating change, and standard deviation from the most recent game
            # either as home or away team
            if team == recent_game['home_team']:
                rating = recent_game['home_rating']
                rating_change = recent_game['ratingChangeHome']
                stddev = recent_game['home_stddev']
            else:
                rating = recent_game['away_rating']
                rating_change = recent_game['ratingChangeAway']
                stddev = recent_game['away_stddev']
        else:
            rating = rating_change = stddev = np.nan    # No games played yet, set to NaN
        
        # Return the statistics as a dictionary, with placeholders for probabilities
        return {
            'team': team,
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'points': points,
            'rating': rating,
            'rating_change': rating_change,
            'stddev': stddev,
            'champion': 0.0,
            'champions_league': 0.0,
            'relegation_to_EFL': 0.0,
            
        }
        
# Example usage:
if __name__ == "__main__":
    # Test for EPL
    # epl_df = pd.read_csv("EPL_data_files/EPLGames2025_NewScrapping.csv")
    # epl_format = BaseFormat(epl_df, 2025, team_abbr_EPL)
    # epl_format.getStandings()
    # epl_df.to_csv("EPL_data_files/EPLGames2025_NewScrapping.csv", index=False)
    
    # Test for FIFA
    fifa_df = pd.read_csv("FIFA_data_files/FIFAGames2025.csv")
    fifa_format = BaseFormat(fifa_df, 2025, team_abbr_FIFA)
    fifa_format.get_fifa_graphs()
    # standings.to_csv("FIFA_data_files/FIFAStandings2025.csv", index=False)
    # fifa_df.to_csv("FIFA_data_files/FIFAGames2025.csv", index=False)
    