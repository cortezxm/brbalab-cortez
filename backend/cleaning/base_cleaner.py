"""
Base data cleaner with shared functionality for sports data validation.

Provides common validation, backup, and error handling functionality
that both EPL and FIFA cleaners can inherit.
"""

import os
import shutil
import pandas as pd
from datetime import datetime
from pathlib import Path


class DataValidationError(Exception):
    """Custom exception for data validation errors"""
    pass


class BaseDataCleaner:
    """
    Base class for sports data cleaning with shared functionality.
    
    Provides:
    - Error tracking and statistics
    - Backup and restore functionality  
    - Basic data validation methods
    - Common utility functions
    """
    
    def __init__(self):
        """Initialize cleaner with empty tracking structures"""
        self.validation_errors = []
        self.removed_rows = []
        self.statistics = {}
        self.backup_path = None
    
    def _create_backup(self, file_path):
        """
        Create timestamped backup of file before cleaning.
        
        Args:
            file_path (str): Path to file to backup
            
        Returns:
            str: Path to backup file
        """
        if not os.path.exists(file_path):
            raise DataValidationError(f"File not found: {file_path}")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{file_path}.backup_{timestamp}"
        
        shutil.copy2(file_path, backup_path)
        self.backup_path = backup_path
        
        return backup_path
    
    def _restore_backup(self, original_path):
        """
        Restore from backup if cleaning fails.
        
        Args:
            original_path (str): Path to original file
        """
        if self.backup_path and os.path.exists(self.backup_path):
            shutil.copy2(self.backup_path, original_path)
            self._cleanup_backup()
    
    def _cleanup_backup(self):
        """Remove backup file after successful cleaning"""
        if self.backup_path and os.path.exists(self.backup_path):
            os.remove(self.backup_path)
            self.backup_path = None
    
    def _validate_required_columns(self, df, required_columns):
        """
        Validate that DataFrame has required columns.
        
        Args:
            df (DataFrame): DataFrame to validate
            required_columns (list): List of required column names
            
        Raises:
            DataValidationError: If required columns missing
        """
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise DataValidationError(f"Missing required columns: {missing_columns}")
    
    def _validate_date_format(self, date_series):
        """
        Validate date column format for pd.to_datetime compatibility.
        
        Args:
            date_series (Series): Pandas series with date values
            
        Returns:
            tuple: (valid_mask, invalid_indices)
        """
        try:
            # Try to convert all dates
            pd.to_datetime(date_series, format='%Y-%m-%d', errors='raise')
            return pd.Series([True] * len(date_series), index=date_series.index), []
            
        except:
            # Check each date individually
            valid_mask = pd.Series([False] * len(date_series), index=date_series.index)
            invalid_indices = []
            
            for idx, date_val in date_series.items():
                try:
                    if pd.isna(date_val):
                        invalid_indices.append(idx)
                        continue
                        
                    # Try to parse date
                    pd.to_datetime(str(date_val), format='%Y-%m-%d')
                    valid_mask[idx] = True
                    
                except:
                    invalid_indices.append(idx)
                    self.validation_errors.append(f"Invalid date format at index {idx}: {date_val}")
            
            return valid_mask, invalid_indices
    
    def _validate_score_range(self, score_series, max_score=35):
        """
        Validate score values are in reasonable range.
        
        Args:
            score_series (Series): Series with score values
            max_score (int): Maximum allowed score
            
        Returns:
            tuple: (valid_mask, invalid_indices)
        """
        valid_mask = pd.Series([True] * len(score_series), index=score_series.index)
        invalid_indices = []
        
        for idx, score in score_series.items():
            # Check if score is valid
            if pd.isna(score):
                invalid_indices.append(idx)
                valid_mask[idx] = False
                self.validation_errors.append(f"NaN score at index {idx}")
                continue
            
            try:
                score_int = int(score)
                if score_int < 0 or score_int > max_score:
                    invalid_indices.append(idx)
                    valid_mask[idx] = False
                    self.validation_errors.append(f"Score out of range at index {idx}: {score_int}")
                    
            except (ValueError, TypeError):
                invalid_indices.append(idx)
                valid_mask[idx] = False
                self.validation_errors.append(f"Invalid score type at index {idx}: {score}")
        
        return valid_mask, invalid_indices
    
    def _normalize_boolean_column(self, series, true_values=None, default_value=False):
        """
        Convert column to boolean with specified true values.
        
        Args:
            series (Series): Series to convert
            true_values (set): Values that should be True
            default_value (bool): Default value for unrecognized values
            
        Returns:
            Series: Boolean series
        """
        if true_values is None:
            true_values = {'yes', 'true', '1', 'y', 't'}
        
        def convert_to_bool(value):
            if pd.isna(value):
                return default_value
            
            str_value = str(value).lower().strip()
            return str_value in true_values
        
        return series.apply(convert_to_bool)
    
    def _remove_rows_by_indices(self, df, indices_to_remove, reason="validation"):
        """
        Remove rows from DataFrame and track removal.
        
        Args:
            df (DataFrame): DataFrame to clean
            indices_to_remove (list): List of indices to remove
            reason (str): Reason for removal
            
        Returns:
            DataFrame: Cleaned DataFrame
        """
        if not indices_to_remove:
            return df
        
        # Track removed rows
        for idx in indices_to_remove:
            self.removed_rows.append({
                'index': idx,
                'reason': reason,
                'data': df.loc[idx].to_dict() if idx in df.index else None
            })
        
        # Remove rows
        cleaned_df = df.drop(indices_to_remove, errors='ignore')
        
        return cleaned_df
    
    def _update_statistics(self, original_count, final_count, stage="cleaning"):
        """
        Update cleaning statistics.
        
        Args:
            original_count (int): Original number of rows
            final_count (int): Final number of rows  
            stage (str): Stage name for statistics
        """
        self.statistics.update({
            f'{stage}_original_count': original_count,
            f'{stage}_final_count': final_count,
            f'{stage}_removed_count': original_count - final_count,
            f'{stage}_validation_errors': len(self.validation_errors),
            f'{stage}_removed_rows': len(self.removed_rows)
        })
    
    def _safe_file_operation(self, file_path, operation_func):
        """
        Safely perform file operation with backup and restore.
        
        Args:
            file_path (str): Path to file
            operation_func (callable): Function that performs the operation
            
        Returns:
            Any: Result from operation_func
        """
        try:
            # Create backup
            self._create_backup(file_path)
            
            # Perform operation
            result = operation_func(file_path)
            
            # Clean up backup on success
            self._cleanup_backup()
            
            return result
            
        except Exception as e:
            # Restore backup on failure
            self._restore_backup(file_path)
            raise DataValidationError(f"File operation failed: {str(e)}")
    
    def get_cleaning_summary(self):
        """
        Get summary of cleaning operation.
        
        Returns:
            dict: Summary with statistics and errors
        """
        return {
            'statistics': self.statistics.copy(),
            'validation_errors_count': len(self.validation_errors),
            'removed_rows_count': len(self.removed_rows),
            'validation_errors': self.validation_errors.copy(),
            'success': len(self.validation_errors) == 0
        }