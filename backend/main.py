"""
Data Pipeline Orchestrator

This is the main entry point for the data processing pipeline.
Orchestrates the complete workflow from data acquisition to final CSV exports.

Pipeline stages:
1. Acquisition: Scrape EPL/FIFA data 
2. Cleaning: Validate and clean scraped data  
3. Processing: Calculate ratings, predictions, standings
4. Export: Generate final CSV files

Usage:
    python main.py                           # Run EPL pipeline (default)
    python main.py --league FIFA            # Run FIFA pipeline
    python main.py --league EPL             # Run EPL pipeline explicitly
    python main.py --step acquisition       # Run single step
    python main.py --league FIFA --confederation UEFA  # Run FIFA UEFA only
"""

import argparse
import sys
import os
import json
from datetime import datetime
from pathlib import Path
import traceback

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import pipeline modules
# Scrapers need Selenium/Playwright and a local Chrome. They are optional so the
# pipeline can also run offline from a data snapshot (e.g. in a notebook).
try:
    from acquisition.scraper import EPLScraper, FIFAScraper, get_epl_season_year
except ImportError:
    EPLScraper = FIFAScraper = None
    def get_epl_season_year():
        now = datetime.now()
        return now.year if now.month >= 8 else now.year - 1
from cleaning.epl_cleaner import EPLDataCleaner
from cleaning.fifa_cleaner import FIFADataCleaner
from cleaning.base_cleaner import DataValidationError
from processing.rating import RatingProcessor, LeagueParameters
from processing.format import BaseFormat
from processing.team_dicts import team_abbr_EPL, team_abbr_FIFA
try:
    from export.export import exporter
except ImportError:
    exporter = None

class DataPipelineOrchestrator:
    """
    Main orchestrator for data pipeline
    Manages the complete workflow from scraping to final outputs
    Supports both EPL and FIFA leagues, with FIFA confederation filtering
    """
    
    def __init__(self, league="EPL", season_year=None, confederation=None, verbose=True,
                 snapshot=None, export_to="gsheets"):
        """
        Initialize pipeline orchestrator
        
        Args:
            league (str): League to process ("EPL" or "FIFA")
            season_year (int, optional): Specific season year to process. 
                                       Defaults to current season.
            confederation (str, optional): FIFA confederation to process 
                                         (UEFA, CAF, AFC, CONCACAF, CONMEBOL, OFC)
            verbose (bool): Enable verbose output
            snapshot (str, optional): Path to a CSV with already-scraped games.
                                      When set, acquisition reads it instead of scraping.
            export_to (str): "gsheets" (production) or "csv" (writes to output/)
        """
        self.league = league.upper()
        self.season_year = season_year or get_epl_season_year()
        self.confederation = confederation.upper() if confederation else None
        self.verbose = verbose
        self.pipeline_results = {}
        self.snapshot = snapshot
        self.export_to = export_to
        self.state_file = Path("acquisition/state.json")
        
        # Validate confederation
        if self.confederation and self.league != "FIFA":
            raise ValueError("Confederation parameter is only valid for FIFA league")
        
        valid_confederations = ['UEFA', 'CAF', 'AFC', 'CONCACAF', 'CONMEBOL', 'OFC']
        if self.confederation and self.confederation not in valid_confederations:
            raise ValueError(f"Invalid confederation. Choose from: {valid_confederations}")
        
        if self.verbose:
            pipeline_desc = f"{self.league}"
            if self.confederation:
                pipeline_desc += f" ({self.confederation})"
            pipeline_desc += f" Pipeline for season {self.season_year}-{self.season_year + 1}"
            print(f"Initializing {pipeline_desc}")
    
    def load_state(self):
        """Load pipeline state from JSON file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            else:
                return {"last_run": {"EPL": None, "FIFA": None}}
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not load state file: {e}")
            return {"last_run": {"EPL": None, "FIFA": None}}
    
    def save_state(self, league, timestamp=None):
        """Save pipeline state to JSON file"""
        try:
            state = self.load_state()
            state_key = league
            if self.confederation:
                state_key = f"{league}_{self.confederation}"
            
            if "last_run" not in state:
                state["last_run"] = {}
            
            state["last_run"][state_key] = timestamp or datetime.now().isoformat()
            
            # Ensure directory exists
            self.state_file.parent.mkdir(exist_ok=True)
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
            if self.verbose:
                print(f"State saved: {state_key} last run updated")
                
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not save state: {e}")
    
    def check_should_run(self, league):
        """Check if league should run based on frequency and last run"""
        state = self.load_state()
        
        state_key = league
        if self.confederation:
            state_key = f"{league}_{self.confederation}"
        
        last_run_str = state["last_run"].get(state_key)
        
        if not last_run_str:
            return True, "First run"
        
        try:
            last_run = datetime.fromisoformat(last_run_str)
            hours_since = (datetime.now() - last_run).total_seconds() / 3600
            
            # Frequency rules (from scraper.py configs)
            # For confederations, use shorter frequency since it's partial data
            if self.confederation:
                frequency_hours = {"FIFA": 720}  # 1 month for confederations
            else:
                frequency_hours = {"EPL": 24, "FIFA": 4320}  # 24h for EPL, 6 months for FIFA
            
            required_hours = frequency_hours.get(league, 24)
            
            if hours_since >= required_hours:
                return True, f"Last run {hours_since:.1f}h ago (required: {required_hours}h)"
            else:
                remaining = required_hours - hours_since
                return False, f"Too soon - {remaining:.1f}h remaining"
                
        except Exception as e:
            return True, f"Could not parse last run time: {e}"
    
    def run_full_pipeline(self):
        """
        Execute the complete data pipeline
        
        Returns:
            dict: Results from each pipeline stage
            
        Raises:
            Exception: If any pipeline stage fails critically
        """
        try:
            if self.verbose:
                pipeline_name = f"{self.league}"
                if self.confederation:
                    pipeline_name += f" {self.confederation}"
                
                print(f"STARTING {pipeline_name} DATA PIPELINE")
                print("="*60)
                
                # Check if should run
                should_run, reason = self.check_should_run(self.league)
                print(f"Run check: {reason}")
                
                if not should_run:
                    print(f"Skipping {pipeline_name} pipeline - {reason}")
                    return {"skipped": True, "reason": reason}
            
            # Stage 1: Data Acquisition
            acquisition_results = self.run_acquisition()
            
            # Stage 2: Data Cleaning
            cleaning_results = self.run_cleaning(acquisition_results)
            
            # Stage 3: Data Processing
            processing_results = self.run_processing(cleaning_results)
            
            # Save files locally for reference
            season_str = str(self.season_year)
            if self.league == "EPL":
                processing_results['processed_data'].to_csv(f'EPL_data_files/EPLGames{season_str}.csv', index=False)
                processing_results['standings'].to_csv(f'EPL_data_files/EPLStandings{season_str}.csv', index=False)
            
            # Stage 4: Data Export
            export_results = self.run_export(processing_results)
            
            # Save successful run state
            self.save_state(self.league)
            
            if self.verbose:
                print("\n" + "="*60)
                pipeline_name = f"{self.league}"
                if self.confederation:
                    pipeline_name += f" {self.confederation}"
                print(f"{pipeline_name} PIPELINE COMPLETED SUCCESSFULLY")
                print("="*60)
                self._print_pipeline_summary()
            
            return self.pipeline_results
            
        except Exception as e:
            pipeline_name = f"{self.league}"
            if self.confederation:
                pipeline_name += f" {self.confederation}"
            print(f"\n{pipeline_name} PIPELINE FAILED: {str(e)}")
            raise
    
    def run_acquisition(self):
        """
        Execute data acquisition stage
        
        Returns:
            dict: Acquisition results with games_df and metadata
        """
        acquisition_desc = f"{'Loading' if self.snapshot else 'Scraping'} {self.league}"
        if self.confederation:
            acquisition_desc += f" {self.confederation}"
        acquisition_desc += " data..."
        
        if self.verbose:
            print(f"\n[1/4] ACQUISITION: {acquisition_desc}")
        
        start_time = datetime.now()
        
        try:
            if self.snapshot:
                return self._run_snapshot_acquisition(start_time)

            # Initialize appropriate scraper
            if self.league == "EPL":
                scraper = EPLScraper()
                games_df, metadata = scraper.scrape_data()
                
                # Calculate teams for EPL
                total_teams = len(set(games_df['home_team'].unique()) | set(games_df['away_team'].unique())) if not games_df.empty else 0
                
            elif self.league == "FIFA":
                scraper = FIFAScraper()
                
                if self.confederation:
                    # Use confederation-specific scraping
                    games_df, metadata = scraper.scrape_confederation(self.confederation)
                    total_teams = metadata.get('confederation_countries', 0)
                else:
                    # Use full FIFA scraping
                    games_df, metadata = scraper.scrape_data()
                    total_teams = metadata.get('successful_countries', 0)
                
            else:
                raise ValueError(f"Unsupported league: {self.league}")
            
            # Store results
            acquisition_results = {
                'league': self.league,
                'confederation': self.confederation,
                'games_df': games_df,
                'metadata': metadata,
                'season_year': scraper.season_year,
                'total_games': len(games_df),
                'total_teams': total_teams,
                'execution_time': (datetime.now() - start_time).total_seconds(),
                'success': metadata.get('success', True)
            }
            
            self.pipeline_results['acquisition'] = acquisition_results
            
            if self.verbose:
                print(f"   Scraped {acquisition_results['total_games']} games")
                print(f"   Found {acquisition_results['total_teams']} teams/countries")
                print(f"   Season: {acquisition_results['season_year']}-{acquisition_results['season_year'] + 1}")
                print(f"   Time: {acquisition_results['execution_time']:.2f}s")
                
                # FIFA specific stats
                if self.league == "FIFA" and metadata.get('success_rate'):
                    print(f"   Success rate: {metadata['success_rate']:.1f}%")
                    print(f"   Venues found: {metadata.get('venues_found', 0)}")
                
                # Confederation specific stats
                if self.confederation:
                    print(f"   Confederation: {self.confederation}")
                    confederation_countries = metadata.get('confederation_countries', 0)
                    print(f"   Countries in confederation: {confederation_countries}")
            
            return acquisition_results
            
        except Exception as e:
            raise Exception(f"Acquisition stage failed: {str(e)}")
    
    def _run_snapshot_acquisition(self, start_time):
        """Load already-scraped games from a CSV snapshot instead of scraping."""
        import pandas as pd
        import shutil

        if self.league == "FIFA":
            # The FIFA scraper writes its output to AllGames.csv, which is what
            # the cleaning stage reads. Reproduce that hand-off from the snapshot.
            shutil.copy(self.snapshot, "FIFA_data_files/AllGames.csv")
        games_df = pd.read_csv(self.snapshot)
        total_teams = len(set(games_df['home_team']) | set(games_df['away_team']))

        acquisition_results = {
            'league': self.league,
            'confederation': self.confederation,
            'games_df': games_df,
            'metadata': {'source': 'snapshot', 'path': str(self.snapshot)},
            'season_year': self.season_year,
            'total_games': len(games_df),
            'total_teams': total_teams,
            'execution_time': (datetime.now() - start_time).total_seconds(),
            'success': True
        }
        self.pipeline_results['acquisition'] = acquisition_results

        if self.verbose:
            print(f"   Loaded {len(games_df)} games from snapshot {self.snapshot}")
            print(f"   Found {total_teams} teams/countries")
            print(f"   Time: {acquisition_results['execution_time']:.2f}s")

        return acquisition_results

    def run_cleaning(self, acquisition_results=None):
        """
        Execute data cleaning stage
        
        Args:
            acquisition_results (dict, optional): Results from acquisition stage.
                                                 Required for EPL, optional for FIFA.
            
        Returns:
            dict: Cleaning results with cleaned data
        """
        if self.verbose:
            print(f"\n[2/4] CLEANING: Validating and cleaning data...")
        
        start_time = datetime.now()
        
        try:
            # Initialize appropriate cleaner
            if self.league == "EPL":
                if acquisition_results is None:
                    raise Exception("EPL cleaning requires acquisition results")
                
                cleaner = EPLDataCleaner()
                
                # Clean EPL data (existing interface)
                games_df = acquisition_results['games_df']
                gameweek_mapping = acquisition_results['metadata'].get('gameweek_mapping', {})
                
                cleaned_games_df, cleaned_gameweek_mapping = cleaner.clean_data(
                    games_df, gameweek_mapping
                )
                
                # EPL-specific results
                cleaning_results = {
                    'games_df': cleaned_games_df,
                    'gameweek_mapping': cleaned_gameweek_mapping,
                    'original_games_count': len(games_df),
                    'cleaned_games_count': len(cleaned_games_df),
                    'removed_games_count': len(games_df) - len(cleaned_games_df),
                    'validation_errors': cleaner.validation_errors,
                    'execution_time': (datetime.now() - start_time).total_seconds()
                }
                
            elif self.league == "FIFA":
                cleaner = FIFADataCleaner()
                
                # Clean FIFA data (file-based interface - no acquisition needed)
                fifa_file = "FIFA_data_files/AllGames.csv"
                cleaning_summary, cleaned_df = cleaner.clean_data(fifa_file)
                
                # FIFA-specific results
                cleaning_results = {
                    'original_games_count': cleaner.statistics.get('fifa_cleaning_original_count', 0),
                    'cleaned_games_count': cleaner.statistics.get('fifa_cleaning_final_count', 0),
                    'removed_games_count': cleaner.statistics.get('fifa_cleaning_removed_count', 0),
                    'validation_errors': cleaner.validation_errors,
                    'execution_time': (datetime.now() - start_time).total_seconds(),
                    'cleaning_summary': cleaning_summary,
                    'games_df': cleaned_df
                }
                
            else:
                return {
                    'skipped': True,
                    'reason': f'Cleaning not implemented for {self.league}',
                    'execution_time': 0
                }
            
            self.pipeline_results['cleaning'] = cleaning_results
            
            if self.verbose:
                print(f"   Processed {cleaning_results['original_games_count']} games")
                print(f"   Cleaned {cleaning_results['cleaned_games_count']} games")
                if cleaning_results['removed_games_count'] > 0:
                    print(f"   Removed {cleaning_results['removed_games_count']} invalid games")
                if cleaner.validation_errors:
                    print(f"   {len(cleaner.validation_errors)} validation warnings: \n")
                print(f"   Time: {cleaning_results['execution_time']:.2f}s")
            
            return cleaning_results
            
        except DataValidationError as e:
            raise Exception(f"Cleaning stage failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Cleaning stage failed: {str(e)}")
        
    def run_processing(self, cleaning_results=None):
        """
        Execute data processing stage
        
        Args:
            cleaning_results (dict, optional): Results from cleaning stage.
        
        Returns:
            dict: Processing results with processed data
        """
        if self.verbose:
            print(f"\n[3/4] PROCESSING: Calculating ratings and predictions...")
        
        start_time = datetime.now()
        
        try:
            # Placeholder for processing logic
            # For now, just pass through cleaned data
            if cleaning_results is None:
                raise Exception("Processing requires cleaning results")
            
            processed_data = cleaning_results['games_df']
            
            # For the rating
            parameters = LeagueParameters(self.league)
            processor = RatingProcessor(parameters)
            processed_data = processor.update_ratings(processed_data)
            
            # For the standings for EPL, and graphs for FIFA
            if self.league == "EPL":
                team_abbr = team_abbr_EPL
                formatter = BaseFormat(processed_data, self.league, team_abbr_EPL)
                standings = formatter.getStandings()
                # For the simulation
                standings = processor.simulate(standings, processed_data)
            elif self.league == "FIFA":
                formatter = BaseFormat(processed_data, self.league, team_abbr_FIFA)
                formatter.get_fifa_graphs()
                standings = None
                
            
            processing_results = {
                'processed_data': processed_data,
                'standings': standings,
                'execution_time': (datetime.now() - start_time).total_seconds()
            }
            
            self.pipeline_results['processing'] = processing_results
            
            if self.verbose:
                print(f"   Processed {len(processed_data)} games")
                print(f"   Time: {processing_results['execution_time']:.2f}s")
            
            return processing_results
            
        except Exception as e:
            print(f"Processing stage failed: {str(e)}")
            traceback.print_exc()
            raise
        
    def run_export(self, processing_results=None):
        """
        Execute data export stage
        
        Args:
            processing_results (dict, optional): Results from processing stage.
        
        Returns:
            dict: Export results with status
        """
        if self.verbose:
            target = "CSV files" if self.export_to == "csv" else "Google Spreadsheets"
            print(f"\n[4/4] EXPORT: Exporting to {target}...")
        
        start_time = datetime.now()
        
        try:
            if processing_results is None:
                raise Exception("Export requires processing results")
            
            if self.export_to == "csv":
                return self._run_csv_export(processing_results, start_time)

            # Placeholder for export logic
            exporter_instance = exporter(
                games=processing_results['processed_data'],
                standings=processing_results['standings'],
                league=self.league,
                year=self.season_year
            )
            exporter_instance.upload_to_gsheets()
            # For now, just simulate export success
            export_results = {
                'status': 'success',
                'execution_time': (datetime.now() - start_time).total_seconds()
            }
            
            self.pipeline_results['export'] = export_results
            
            if self.verbose:
                print(f"   Export status: {export_results['status']}")
                print(f"   Time: {export_results['execution_time']:.2f}s")
            
            return export_results
            
        except Exception as e:
            print(f"Processing stage failed: {str(e)}")
            traceback.print_exc()
            raise
    
    def _run_csv_export(self, processing_results, start_time):
        """Write the export tables to output/ instead of Google Sheets."""
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        files = []
        for name in ('processed_data', 'standings'):
            df = processing_results.get(name)
            if df is not None:
                path = out_dir / f"{self.league}_{name}.csv"
                df.to_csv(path, index=False)
                files.append(str(path))

        export_results = {
            'status': 'success',
            'files': files,
            'execution_time': (datetime.now() - start_time).total_seconds()
        }
        self.pipeline_results['export'] = export_results

        if self.verbose:
            print(f"   Wrote {', '.join(files)}")
            print(f"   Time: {export_results['execution_time']:.2f}s")

        return export_results

    def _print_pipeline_summary(self):
        """Print summary of pipeline execution"""
        print(f"\nPIPELINE SUMMARY:")
        
        if 'acquisition' in self.pipeline_results:
            acq = self.pipeline_results['acquisition']
            summary_line = f"   Acquisition: {acq['total_games']} games, {acq['total_teams']} teams/countries"
            if self.confederation:
                summary_line += f" ({self.confederation})"
            print(summary_line)
        
        if 'cleaning' in self.pipeline_results and not self.pipeline_results['cleaning'].get('skipped'):
            clean = self.pipeline_results['cleaning']
            print(f"   Cleaning: {clean['cleaned_games_count']}/{clean['original_games_count']} games validated")
        
        total_time = sum(
            stage.get('execution_time', 0) 
            for stage in self.pipeline_results.values() 
            if isinstance(stage, dict) and not stage.get('skipped')
        )
        print(f"   Total execution time: {total_time:.2f}s")
    
    def run_single_step(self, step_name):
        """
        Run a single pipeline step
        
        Args:
            step_name (str): Name of step to run ('acquisition', 'cleaning', etc.)
        """
        if step_name == 'acquisition':
            return self.run_acquisition()
        elif step_name == 'cleaning':
            # FIFA cleaning can work standalone (uses existing file)
            # EPL cleaning needs acquisition results
            if self.league == "FIFA":
                return self.run_cleaning()  # No acquisition needed for FIFA
            else:
                # EPL needs acquisition results first
                acquisition_results = self.run_acquisition()
                return self.run_cleaning(acquisition_results)
        elif step_name == 'processing':
            print("Processing step not yet implemented")
        elif step_name == 'export':
            print("Export step not yet implemented")
        else:
            raise ValueError(f"Unknown step: {step_name}")


def main():
    """
    Main entry point for data pipeline
    """
    parser = argparse.ArgumentParser(description='Data Pipeline for EPL and FIFA')
    parser.add_argument('--league', choices=['EPL', 'FIFA'], default='EPL',
                       help='League to process (default: EPL)')
    parser.add_argument('--confederation', choices=['UEFA', 'CAF', 'AFC', 'CONCACAF', 'CONMEBOL', 'OFC'],
                       help='FIFA confederation to process (only valid with --league FIFA)')
    parser.add_argument('--step', choices=['acquisition', 'cleaning', 'processing', 'export'],
                       help='Run specific pipeline step only')
    parser.add_argument('--quiet', action='store_true', help='Reduce output verbosity')
    parser.add_argument('--force', action='store_true', help='Force run regardless of frequency')
    
    args = parser.parse_args()
    
    # Validate confederation usage
    if args.confederation and args.league != 'FIFA':
        parser.error("--confederation can only be used with --league FIFA")
    
    try:
        # Initialize orchestrator
        orchestrator = DataPipelineOrchestrator(
            league=args.league,
            confederation=args.confederation,
            verbose=not args.quiet
        )
        
        # Override frequency check if forced
        if args.force:
            orchestrator.check_should_run = lambda league: (True, "Forced run")
        
        # Run pipeline
        if args.step:
            # Run single step
            orchestrator.run_single_step(args.step)
        else:
            # Run full pipeline
            result = orchestrator.run_full_pipeline()
            
            # Handle skipped runs
            if result.get('skipped'):
                pipeline_name = args.league
                if args.confederation:
                    pipeline_name += f" {args.confederation}"
                print(f"\n{pipeline_name} pipeline was skipped: {result['reason']}")
                print("Use --force to run anyway")
                                
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()