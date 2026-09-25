"""
EPL-specific data cleaner for English Premier League data.

Handles EPL-specific validation, normalization and cleaning requirements
including gameweek mapping and team name standardization.
"""

import pandas as pd
from .base_cleaner import BaseDataCleaner, DataValidationError


class EPLDataCleaner(BaseDataCleaner):
    """
    Data cleaner for EPL (English Premier League) data.
    
    Validates and cleans EPL games data and gameweek mapping
    with EPL-specific business rules and requirements.
    """
    
    def __init__(self):
        """Initialize EPL cleaner"""
        super().__init__()
    
    def clean_data(self, games_df, gameweek_mapping):
        """
        Clean EPL games data and gameweek mapping.
        
        Args:
            games_df (DataFrame): Raw EPL games data
            gameweek_mapping (dict): Gameweek to date mapping
            
        Returns:
            tuple: (cleaned_games_df, cleaned_gameweek_mapping)
            
        Raises:
            DataValidationError: If validation fails
        """
        try:
            if games_df.empty:
                return games_df, gameweek_mapping
            
            original_count = len(games_df)
            
            # Validate required columns for EPL
            self._validate_epl_columns(games_df)
            
            # Clean games data
            cleaned_games_df = self._clean_epl_games(games_df)
            
            # Clean gameweek mapping
            cleaned_gameweek_mapping = self._clean_gameweek_mapping(gameweek_mapping)
            
            # Update statistics
            final_count = len(cleaned_games_df)
            self._update_statistics(original_count, final_count, "epl_cleaning")
            
            return cleaned_games_df, cleaned_gameweek_mapping
            
        except Exception as e:
            raise DataValidationError(f"EPL data cleaning failed: {str(e)}")
    
    def _validate_epl_columns(self, df):
        """
        Validate EPL-specific required columns.
        
        Args:
            df (DataFrame): EPL games DataFrame
        """
        # EPL expected columns (flexible - may vary by scraper)
        core_columns = ['date', 'home_team', 'away_team']
        
        # Check core columns exist
        missing_core = [col for col in core_columns if col not in df.columns]
        if missing_core:
            raise DataValidationError(f"Missing core EPL columns: {missing_core}")
    
    def _clean_epl_games(self, df):
        """
        Clean EPL games DataFrame.
        
        Args:
            df (DataFrame): Raw EPL games data
            
        Returns:
            DataFrame: Cleaned EPL games data
        """
        # Make copy to avoid modifying original
        cleaned_df = df.copy()
        
        # 1. Validate and clean dates
        cleaned_df = self._clean_epl_dates(cleaned_df)
        
        # 2. Validate and clean team names
        cleaned_df = self._clean_epl_teams(cleaned_df)
        
        # 3. Validate and clean scores (if present)
        if 'home_score' in cleaned_df.columns and 'away_score' in cleaned_df.columns:
            cleaned_df = self._clean_epl_scores(cleaned_df)
        
        # 4. Remove invalid rows
        cleaned_df = self._remove_invalid_epl_rows(cleaned_df)
        
        return cleaned_df
    
    def _clean_epl_dates(self, df):
        """
        Clean and validate EPL date columns.
        
        Args:
            df (DataFrame): EPL games DataFrame
            
        Returns:
            DataFrame: DataFrame with cleaned dates
        """
        if 'date' not in df.columns:
            return df
        
        # Validate date format
        valid_mask, invalid_indices = self._validate_date_format(df['date'])
        
        # Remove rows with invalid dates
        if invalid_indices:
            df = self._remove_rows_by_indices(df, invalid_indices, "invalid_date")
        
        return df
    
    def _clean_epl_teams(self, df):
        """
        Clean and normalize EPL team names.
        
        Args:
            df (DataFrame): EPL games DataFrame
            
        Returns:
            DataFrame: DataFrame with normalized team names
        """
        # EPL team name normalizations
        team_normalizations = {
            'Manchester City': 'Manchester City',
            'Man City': 'Manchester City',
            'Manchester Utd': 'Manchester United',
            'Man United': 'Manchester United',
            'Man Utd': 'Manchester United',
            'Newcastle Utd': 'Newcastle United',
            'Sheffield Utd': 'Sheffield United',
            'Brighton': 'Brighton & Hove Albion',
            'Wolves': 'Wolverhampton Wanderers',
            'Nott\'ham Forest': 'Nottingham Forest',
            'Nottm Forest': 'Nottingham Forest'
        }
        
        # Apply normalizations to team columns
        for col in ['home_team', 'away_team']:
            if col in df.columns:
                df[col] = df[col].replace(team_normalizations)
                
                # Remove extra whitespace
                df[col] = df[col].astype(str).str.strip()
                
        return df
    
    def _clean_epl_scores(self, df):
        """
        Clean and validate EPL scores.
        
        Args:
            df (DataFrame): EPL games DataFrame
            
        Returns:
            DataFrame: DataFrame with validated scores
        """
        score_columns = ['home_score', 'away_score']
        invalid_rows = []
        
        for col in score_columns:
            if col in df.columns:
                # Validate score range (EPL allows -1 for future games, 0-15 for played games)
                valid_mask, invalid_indices = self._validate_epl_score_range(df[col])
                invalid_rows.extend(invalid_indices)
        
        # Remove rows with invalid scores
        if invalid_rows:
            unique_invalid = list(set(invalid_rows))
            df = self._remove_rows_by_indices(df, unique_invalid, "invalid_score")
        
        return df
    
    def _validate_epl_score_range(self, score_series):
        """
        Validate EPL score values with special handling for -1 (future games).
        
        Args:
            score_series (Series): Series with score values
            
        Returns:
            tuple: (valid_mask, invalid_indices)
        """
        valid_mask = pd.Series([True] * len(score_series), index=score_series.index)
        invalid_indices = []
        
        for idx, score in score_series.items():
            # Check if score is valid
            if pd.isna(score):
                # NaN is allowed (future games)
                continue
            
            try:
                score_int = int(score)
                
                # EPL special case: -1 is valid (represents future/unplayed games)
                if score_int == -1:
                    continue
                
                # Regular validation for played games: 0-15
                if score_int < 0 or score_int > 15:
                    invalid_indices.append(idx)
                    valid_mask[idx] = False
                    self.validation_errors.append(f"Score out of range at index {idx}: {score_int}")
                    
            except (ValueError, TypeError):
                invalid_indices.append(idx)
                valid_mask[idx] = False
                self.validation_errors.append(f"Invalid score type at index {idx}: {score}")
        
        return valid_mask, invalid_indices
    
    def _remove_invalid_epl_rows(self, df):
        """
        Remove rows that don't meet EPL data quality requirements.
        
        Args:
            df (DataFrame): EPL games DataFrame
            
        Returns:
            DataFrame: DataFrame with invalid rows removed
        """
        invalid_indices = []
        
        for idx, row in df.iterrows():
            # Check for completely empty team names
            if 'home_team' in df.columns and 'away_team' in df.columns:
                if pd.isna(row['home_team']) or pd.isna(row['away_team']):
                    invalid_indices.append(idx)
                    continue
                    
                if str(row['home_team']).strip() == '' or str(row['away_team']).strip() == '':
                    invalid_indices.append(idx)
                    continue
            
            # Check for same team playing itself
            if 'home_team' in df.columns and 'away_team' in df.columns:
                if row['home_team'] == row['away_team']:
                    invalid_indices.append(idx)
                    continue
        
        # Remove invalid rows
        if invalid_indices:
            df = self._remove_rows_by_indices(df, invalid_indices, "epl_business_rules")

        print(df)
        
        return df
    
    def _clean_gameweek_mapping(self, gameweek_mapping):
        """
        Clean and validate gameweek mapping.
        
        Args:
            gameweek_mapping (dict): Gameweek to date mapping
            
        Returns:
            dict: Cleaned gameweek mapping
        """
        if not gameweek_mapping:
            return gameweek_mapping
        
        cleaned_mapping = {}
        
        for gameweek, date_value in gameweek_mapping.items():
            try:
                # Validate gameweek key
                if pd.isna(gameweek) or str(gameweek).strip() == '':
                    continue
                
                # Validate date value
                if pd.isna(date_value) or str(date_value).strip() == '':
                    continue
                
                # Try to parse date to ensure it's valid
                pd.to_datetime(str(date_value))
                
                cleaned_mapping[gameweek] = date_value
                
            except Exception as e:
                self.validation_errors.append(f"Invalid gameweek mapping - {gameweek}: {date_value} - {str(e)}")
                continue
        
        return cleaned_mapping