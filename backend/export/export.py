"""
Export Utilities for Sports League Data

This module provides tools for exporting processed league data (games and standings)
to Google Sheets for sharing, visualization, or further analysis. It supports exporting
to multiple worksheets within a spreadsheet, including both season-specific and 'current' views.

Main components:
    - exporter: Class for uploading DataFrames to Google Sheets, handling worksheet creation and updates.

Key features:
    - Uploads games and standings DataFrames to Google Sheets.
    - Supports exporting to both season-specific and 'current' worksheets.
    - Handles Google authentication using a service account JSON key.
    - Designed for extensibility to other leagues and data formats.

Typical usage:
    games = games_df  # DataFrame of game data
    standings = standings_df  # DataFrame of standings data
    exporter_instance = exporter(games, standings, 2025, 'EPL')
    exporter_instance.upload_to_gsheets()
"""
import pandas as pd
from abc import ABC
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class exporter(ABC):
    """
    Handles exporting league data (games and standings) to Google Sheets.

    This class provides methods to upload DataFrames to specific worksheets within a Google Spreadsheet,
    supporting both season-specific and 'current' views. It manages Google authentication using a service
    account and ensures worksheets are created or updated as needed.

    Attributes:
        games (pd.DataFrame): DataFrame containing game data for the league.
        standings (pd.DataFrame): DataFrame containing standings data for the league.
        year (int): Season year.
        league (str): League identifier (e.g., 'EPL').
        credentials_file (str): Path to the Google service account credentials JSON file.

    Methods:
        upload_to_gsheets(): Uploads games and standings DataFrames to Google Sheets, updating both
            the season-specific worksheet and the 'current' worksheet with the latest data.
    """
    def __init__(self, games, standings, year, league, credentials_file='brbalaboratory.json'):
        """
        Initializes the exporter with league data and configuration.

        Args:
            games (pd.DataFrame): DataFrame containing game data for the league.
            standings (pd.DataFrame): DataFrame containing standings data for the league.
            year (int): Season year.
            league (str): League identifier (e.g., 'EPL').
            credentials_file (str): Path to the Google service account credentials JSON file.
        """
        self.games = games
        self.standings = standings
        self.year = year
        self.league = league
        self.credentials_file = os.path.join(os.path.dirname(__file__), credentials_file)
        
    def upload_to_gsheets(self):
        """
        Uploads games and standings DataFrames to Google Sheets.

        For both games and standings, this method:
            - Uploads the full season data to a worksheet named after the season year.
            - Uploads the current season's data (up to the latest played week plus the next 5 scheduled games)
            to a worksheet named 'current'.
            - Handles worksheet creation or clearing as needed.
            - Authenticates using the provided Google service account credentials.

        Note:
            Currently, exporting for 'FIFA' leagues is not implemented.

        Returns:
            None
        """
        if self.league == 'FIFA':
            return # Not currently implemented for FIFA
        scope = [   # Define the scopes for Google Sheets and Drive API
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Authenticate and create the gspread client
        credentials = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_file, scope)
        client = gspread.authorize(credentials)
        
        # Define spreadsheet names based on league
        spreadsheet_name_games = f'{self.league}_games_Main'
        spreadsheet_name_standings = f'{self.league}_standings_Main'
        
        # Convert DataFrames to list of lists (including header)
        games_data = [self.games.columns.tolist()] + self.games.astype(str).values.tolist()
        standings_data = [self.standings.columns.tolist()] + self.standings.astype(str).values.tolist()
        
        # Upload games
        sh_games = client.open(spreadsheet_name_games)
        
        # Upload standings
        sh_standings = client.open(spreadsheet_name_standings)
        
        # For the games of the the specific season year
        try:
            worksheet_games = sh_games.add_worksheet(title=str(self.year), rows=str(len(games_data)), cols=str(len(games_data[0])))
        except Exception:
            worksheet_games = sh_games.worksheet(str(self.year))
            worksheet_games.clear()
        worksheet_games.append_rows(games_data)

        # For standings of the specific season year
        try:
            worksheet_standings = sh_standings.add_worksheet(title=str(self.year), rows=str(len(standings_data)), cols=str(len(standings_data[0])))
        except Exception:
            worksheet_standings = sh_standings.worksheet(str(self.year))
            worksheet_standings.clear()
        worksheet_standings.append_rows(standings_data)
        
        # For the current season
        self.games['gameweek'] = self.games['gameweek'].astype(int)
        # Filter and quit the rows where home_score and away_score are -1
        current_games = self.games[(self.games['home_score'] != -1) & (self.games['away_score'] != -1)].copy()
        current_week = current_games['gameweek'].max()
        
        # Add first 5 pending games
        pending_games = self.games[(self.games['home_score'] == -1) & (self.games['away_score'] == -1)].copy()
        pending_games = pending_games.head(5)
        current_games = pd.concat([current_games, pending_games], ignore_index=True)
        
        current_standings = self.standings[self.standings['week'] <= current_week]
        current_games_data = [current_games.columns.tolist()] + current_games.astype(str).values.tolist()
        current_standings_data = [current_standings.columns.tolist()] + current_standings.astype(str).values.tolist()
        
        # For the games of the current season
        try:
            worksheet_games = sh_games.add_worksheet(title='current', rows=str(len(current_games_data)), cols=str(len(current_games_data[0])))
        except Exception:
            worksheet_games = sh_games.worksheet('current')
            worksheet_games.clear()
        worksheet_games.append_rows(current_games_data)
        
        # For the standings of the current season
        try:
            worksheet_standings = sh_standings.add_worksheet(title='current', rows=str(len(current_standings_data)), cols=str(len(current_standings_data[0])))
        except Exception:
            worksheet_standings = sh_standings.worksheet('current')
            worksheet_standings.clear()
        worksheet_standings.append_rows(current_standings_data)
        return
        

# Test
if __name__ == "__main__":
    games = pd.read_csv("EPL_data_files/EPLGames2025_NewScrapping.csv")
    standings = pd.read_csv("EPL_data_files/EPLStandings2025_NewScrapping.csv")
    exporter_instance = exporter(games, standings, 2025, 'EPL')
    exporter_instance.upload_to_gsheets()