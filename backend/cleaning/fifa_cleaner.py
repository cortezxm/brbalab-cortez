"""
FIFA-specific data cleaner for international football data.

Handles FIFA-specific validation, normalization and cleaning requirements
including competition standardization, result parsing, and venue handling.
"""

import pandas as pd
import re
from .base_cleaner import BaseDataCleaner, DataValidationError


class FIFADataCleaner(BaseDataCleaner):
    """
    Data cleaner for FIFA international football data.
    
    Processes FIFA games data with international-specific business rules,
    competition normalization, and result parsing.
    """
    
    def __init__(self):
        """Initialize FIFA cleaner with competition mappings"""
        super().__init__()
        
        # Competition normalization mappings
        self.competition_mappings = {
            # World Cup variations
            'FIFA World Cup': 'World Cup',
            'World Cup Qualif.': 'World Cup Qualifiers',
            'WC': 'World Cup',
            'WCQ': 'World Cup Qualifiers',
            'World Cup Qualification': 'World Cup Qualifiers',
            'FIFA WC': 'World Cup',
            
            # Continental - UEFA
            'UEFA European Championship': 'European Championship',
            'Euro': 'European Championship', 
            'EURO': 'European Championship',
            'European Championship Qualif.': 'European Championship Qualifiers',
            'Euro Qualif.': 'European Championship Qualifiers',
            'European Qualifiers': 'European Championship Qualifiers',
            'UEFA Nations League': 'Nations League',
            'Nations League': 'Nations League',
            
            # Continental - Other
            'Africa Cup of Nations': 'Africa Cup of Nations',
            'AFCON': 'Africa Cup of Nations',
            'Copa América': 'Copa America',
            'Copa America': 'Copa America',
            'Asian Cup': 'Asian Cup',
            'Gold Cup': 'Gold Cup',
            'OFC Nations Cup': 'OFC Nations Cup',
            
            # Friendlies
            'International Friendly': 'International Friendly',
            'Friendly': 'International Friendly',
            'Int. Friendly': 'International Friendly',
            'Friendlies': 'International Friendly',
            
            # Confederations Cup
            'FIFA Confederations Cup': 'Confederations Cup',
            'Confederations Cup': 'Confederations Cup',
        }
    
    def clean_data(self, file_path="FIFA_data_files/AllGames_raw.csv"):
        """
        Clean FIFA data file in-place with backup protection.
        
        Args:
            file_path (str): Path to FIFA games CSV file
            
        Returns:
            dict: Cleaning summary and statistics
        """
        def _clean_operation(file_path):
            # Load data
            df = pd.read_csv(file_path)
            original_count = len(df)
            
            if self.verbose:
                print(f"   Loaded {original_count} games from {file_path}")
            
            # Clean data
            cleaned_df = self._full_cleaning_pipeline(df)
            
            # Save cleaned data back to same file
            cleaned_df.to_csv(file_path, index=False)
            
            # Update statistics
            final_count = len(cleaned_df)
            self._update_statistics(original_count, final_count, "fifa_cleaning")
            
            if self.verbose:
                print(f"   Saved {final_count} cleaned games to {file_path}")
            
            return self.get_cleaning_summary(), cleaned_df  # Return cleaned DataFrame for further use if needed
        
        # Add verbose flag for internal logging
        self.verbose = True  # Enable internal logging
        
        # Use safe file operation with backup
        return self._safe_file_operation(file_path, _clean_operation)
    
    def _full_cleaning_pipeline(self, df):
        """
        Complete FIFA data cleaning pipeline.
        
        Args:
            df (DataFrame): Raw FIFA games data
            
        Returns:
            DataFrame: Cleaned FIFA games data
        """
        if df.empty:
            return df
        
        # 1. Validate input columns
        self._validate_fifa_columns(df)
        
        # 2. Rename columns: home->home_team, away->away_team
        df = self._rename_fifa_columns(df)
        
        # 3. Process results: split into home_score, away_score
        df = self._process_fifa_results(df)
        
        # 4. Normalize competition names
        df = self._normalize_fifa_competitions(df)
        
        # 5. Convert neutral_pitch to boolean (default: False)
        df = self._normalize_fifa_neutral_pitch(df)
        
        # 6. Validate and clean dates
        df = self._clean_fifa_dates(df)
        
        # 7. Normalize team names
        df = self._normalize_fifa_teams(df)
        
        # 8. Generate unique IDs and remove duplicates
        df = self._generate_fifa_ids_and_dedupe(df)
        
        # 9. Final validation
        df = self._final_fifa_validation(df)
        
        return df
    
    def _validate_fifa_columns(self, df):
        """
        Validate FIFA-specific required columns.
        
        Args:
            df (DataFrame): FIFA games DataFrame
        """
        # Check if we have the core columns in either format
        # Format 1: Raw from scraper (home, away, result)
        # Format 2: Already processed (home_team, away_team, home_score, away_score)
        
        has_raw_format = all(col in df.columns for col in ['home', 'away'])
        has_processed_format = all(col in df.columns for col in ['home_team', 'away_team'])
        
        if not has_raw_format and not has_processed_format:
            raise DataValidationError(
                "Missing required columns. Expected either:\n"
                "- Raw format: ['date', 'home', 'away'] or\n"
                "- Processed format: ['date', 'home_team', 'away_team']"
            )
        
        # Must have date in either case
        if 'date' not in df.columns:
            raise DataValidationError("Missing required 'date' column")
    
    def _rename_fifa_columns(self, df):
        """
        Rename FIFA columns to standard format if needed.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
        Returns:
            DataFrame: DataFrame with renamed columns
        """
        # Check if columns need renaming
        if 'home' in df.columns and 'away' in df.columns:
            # Raw format - rename to standard
            column_renames = {
                'home': 'home_team',
                'away': 'away_team'
            }
            df = df.rename(columns=column_renames)
        
        # If already have home_team, away_team - no renaming needed
        return df
    
    def _process_fifa_results(self, df):
        """
        Process FIFA result column into home_score and away_score.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
        Returns:
            DataFrame: DataFrame with score columns
        """
        # Check if scores already exist
        if 'home_score' in df.columns and 'away_score' in df.columns:
            # Scores already exist - validate and clean them
            return self._validate_existing_scores(df)
        
        # No existing scores - process from result column
        if 'result' not in df.columns:
            # No result column either - create empty score columns
            df['home_score'] = None
            df['away_score'] = None
            return df
        
        # Process result column into scores
        home_scores = []
        away_scores = []
        rows_to_remove = []
        
        for idx, result in df['result'].items():
            home_score, away_score, removal_reason = self._parse_fifa_result(result)
            
            if removal_reason and removal_reason.startswith("REMOVE"):
                rows_to_remove.append(idx)
                home_scores.append(None)
                away_scores.append(None)
            else:
                home_scores.append(home_score)
                away_scores.append(away_score)
        
        # Add score columns
        df['home_score'] = home_scores
        df['away_score'] = away_scores
        
        # Remove problematic rows
        if rows_to_remove:
            df = self._remove_rows_by_indices(df, rows_to_remove, "invalid_result")
        
        return df
    
    def _validate_existing_scores(self, df):
        """
        Validate existing home_score and away_score columns.
        
        Args:
            df (DataFrame): FIFA games DataFrame with existing scores
            
        Returns:
            DataFrame: DataFrame with validated scores
        """
        invalid_rows = []
        
        for idx, row in df.iterrows():
            home_score = row.get('home_score')
            away_score = row.get('away_score')
            
            # Check if scores are valid
            if pd.isna(home_score) or pd.isna(away_score):
                continue  # Allow NaN scores (future games)
            
            try:
                home_int = int(float(home_score))  # Convert float to int
                away_int = int(float(away_score))  # Convert float to int
                
                # Validate reasonable scores (max 35)
                if home_int < 0 or away_int < 0:
                    invalid_rows.append(idx)
                    continue
                    
                if home_int > 35 or away_int > 35:
                    invalid_rows.append(idx)
                    continue
                
                # Update with integer values
                df.at[idx, 'home_score'] = home_int
                df.at[idx, 'away_score'] = away_int
                    
            except (ValueError, TypeError):
                invalid_rows.append(idx)
                continue
        
        # Remove invalid rows
        if invalid_rows:
            df = self._remove_rows_by_indices(df, invalid_rows, "invalid_existing_scores")
        
        return df
    
    def _parse_fifa_result(self, result):
        """
        Parse FIFA result string into scores.
        
        Args:
            result (str): Result string
            
        Returns:
            tuple: (home_score, away_score, removal_reason)
        """
        if pd.isna(result) or str(result).strip() == "":
            return None, None, None
        
        result_str = str(result).strip()
        
        # Check for special cases that should be removed
        special_cases_to_remove = ['awarded', 'walkover', 'w/o', 'postponed', 'cancelled', 'suspended']
        
        for case in special_cases_to_remove:
            if case in result_str.lower():
                return None, None, f"REMOVE: {case}"
        
        # Remove extra info (a.e.t., penalties, etc.)
        clean_result = re.sub(r'\s*(a\.e\.t\.|aet|after extra time).*', '', result_str, flags=re.IGNORECASE)
        clean_result = re.sub(r'\s*\(\d+:\d+\).*', '', clean_result)
        clean_result = clean_result.strip()
        
        # Extract main score
        score_match = re.search(r'(\d+)[:\-](\d+)', clean_result)
        
        if score_match:
            home_score = int(score_match.group(1))
            away_score = int(score_match.group(2)) 
            
            # Validate reasonable scores (max 35)
            if home_score > 35 or away_score > 35:
                return None, None, f"REMOVE: Unrealistic score {home_score}:{away_score}"
            
            return home_score, away_score, None
        
        # Could not parse - return None but don't remove
        return None, None, f"Could not parse: {result_str}"
    
    def _normalize_fifa_competitions(self, df):
        """
        Normalize FIFA competition names.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
        Returns:
            DataFrame: DataFrame with normalized competitions
        """
        if 'competition' not in df.columns:
            df['competition'] = 'Unknown Competition'
            return df
        
        def normalize_competition(competition_name):
            if pd.isna(competition_name) or str(competition_name).strip() == '':
                return 'Unknown Competition'
            
            # Clean input
            clean_name = str(competition_name).strip()
            
            # Exact match (case insensitive)
            for key, value in self.competition_mappings.items():
                if clean_name.lower() == key.lower():
                    return value
            
            # Keep original if no match found
            return clean_name
        
        df['competition'] = df['competition'].apply(normalize_competition)
        
        return df
    
    def _normalize_fifa_neutral_pitch(self, df):
        """
        Convert neutral_pitch to boolean with False default.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
        Returns:
            DataFrame: DataFrame with boolean neutral_pitch
        """
        if 'neutral_pitch' not in df.columns:
            df['neutral_pitch'] = False
            return df
        
        # Use inherited boolean normalization with False default
        true_values = {'yes', 'true', '1', 'neutral', 'y', 't', True, 1}
        df['neutral_pitch'] = self._normalize_boolean_column(df['neutral_pitch'], true_values, default_value=False)
        
        return df
    
    def _clean_fifa_dates(self, df):
        """
        Clean and validate FIFA date columns.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
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
    
    def _normalize_fifa_teams(self, df):
        """
        Normalize FIFA team/country names - minimal changes to preserve FIFA codes.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
        Returns:
            DataFrame: DataFrame with normalized team names
        """
        # Basic team name cleaning - preserve FIFA codes
        for col in ['home_team', 'away_team']:
            if col in df.columns:
                # Remove extra whitespace only
                df[col] = df[col].astype(str).str.strip()
                
                # Only fix obvious typos, NOT FIFA code conversions
                # Keep USA as USA, not "United States"
                # Keep other FIFA codes as-is
                df[col] = df[col].replace({
                    'Türkiye': 'TUR',  # Use FIFA code consistently
                })
        
        return df
    
    def _generate_fifa_ids_and_dedupe(self, df):
        """
        Generate unique IDs and remove duplicates.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
        Returns:
            DataFrame: DataFrame with IDs and duplicates removed
        """
        # Generate unique IDs if not already present
        if 'id' not in df.columns:
            df['id'] = df.apply(self._generate_fifa_game_id, axis=1)
        
        # Find and remove duplicates
        duplicates = df.duplicated(subset=['id'], keep='first')
        duplicate_indices = df[duplicates].index.tolist()
        
        if duplicate_indices:
            df = self._remove_rows_by_indices(df, duplicate_indices, "duplicate_game")
        
        return df
    
    def _generate_fifa_game_id(self, row):
        """
        Generate unique game ID for FIFA game.
        
        Args:
            row (Series): Game row
            
        Returns:
            str: Unique game identifier
        """
        date = str(row.get('date', ''))
        home_team = str(row.get('home_team', ''))
        away_team = str(row.get('away_team', ''))
        
        # Handle empty values
        if not date or not home_team or not away_team:
            return f"invalid_{row.name}" if hasattr(row, 'name') else "invalid"
        
        # Sort teams alphabetically for consistent ID
        teams = sorted([home_team, away_team])
        
        # Create simple ID: date_team1_team2
        game_id = f"{date},{teams[0]},{teams[1]}"
        
        # Clean ID (remove spaces, special chars, keep only alphanumeric, comma, hyphen)
        game_id = re.sub(r'[^\w\,\-]', ',', game_id)

        return game_id
    
    def _final_fifa_validation(self, df):
        """
        Final validation for FIFA data quality and column ordering.
        
        Args:
            df (DataFrame): FIFA games DataFrame
            
        Returns:
            DataFrame: Final validated DataFrame with correct columns
        """
        invalid_indices = []
        
        for idx, row in df.iterrows():
            # Check for completely empty team names
            if pd.isna(row.get('home_team')) or pd.isna(row.get('away_team')):
                invalid_indices.append(idx)
                continue
                
            if str(row.get('home_team', '')).strip() == '' or str(row.get('away_team', '')).strip() == '':
                invalid_indices.append(idx)
                continue
            
            # Check for same team playing itself
            if row.get('home_team') == row.get('away_team'):
                invalid_indices.append(idx)
                continue
        
        # Remove invalid rows
        if invalid_indices:
            df = self._remove_rows_by_indices(df, invalid_indices, "final_validation")
        
        # Ensure all required columns exist with defaults
        required_columns = {
            'date': '',
            'home_team': '',
            'away_team': '',
            'home_score': None,
            'away_score': None,
            'pso': None,
            'competition': 'Unknown Competition',
            'neutral_pitch': False,
            'id': ''
        }
        
        for col, default_value in required_columns.items():
            if col not in df.columns:
                df[col] = default_value
        
        # Convert scores to proper int type
        for score_col in ['home_score', 'away_score']:
            df[score_col] = pd.to_numeric(df[score_col], errors='coerce')
            # Convert to int where not NaN, keep NaN for future games
            df[score_col] = df[score_col].apply(lambda x: int(x) if pd.notna(x) else x)
        
        # Remove unwanted columns (like original 'result', 'index')
        columns_to_keep = list(required_columns.keys())
        df = df[columns_to_keep]
        
        return df