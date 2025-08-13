"""
Google Ad Manager Reporting Service

Provides comprehensive reporting data from GAM including:
- Spend and impression numbers by advertiser, order, and line item
- Three date range options: lifetime by day, this month by day, today by hour
- Timezone handling and data freshness timestamps
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, asdict
import pytz
import gzip
import io
import csv
import time
import tempfile
import logging
from googleads import ad_manager

logger = logging.getLogger(__name__)

@dataclass
class ReportingData:
    """Container for reporting data with metadata"""
    data: List[Dict[str, Any]]
    start_date: datetime
    end_date: datetime
    requested_timezone: str
    data_timezone: str
    data_valid_until: datetime
    query_type: str
    dimensions: List[str]
    metrics: Dict[str, Any]

class GAMReportingService:
    """Service for getting comprehensive reporting data from Google Ad Manager"""
    
    def __init__(self, gam_client, network_timezone: str = None):
        """
        Initialize the reporting service
        
        Args:
            gam_client: Initialized Google Ad Manager client
            network_timezone: The timezone of the GAM network (will be auto-detected if not provided)
        """
        self.client = gam_client
        self.report_service = self.client.GetService('ReportService')
        self.report_downloader = self.client.GetDataDownloader()
        
        # Get network timezone from GAM if not provided
        if network_timezone:
            self.network_timezone = network_timezone
        else:
            try:
                network_service = self.client.GetService('NetworkService')
                network = network_service.getCurrentNetwork()
                self.network_timezone = network.timeZone
            except Exception:
                # Fallback to Eastern Time if we can't get network timezone
                self.network_timezone = "America/New_York"
        
    def get_reporting_data(
        self,
        date_range: Literal["lifetime", "this_month", "today"],
        advertiser_id: Optional[str] = None,
        order_id: Optional[str] = None,
        line_item_id: Optional[str] = None,
        requested_timezone: str = "America/New_York"
    ) -> ReportingData:
        """
        Get reporting data for specified date range and filters
        
        Args:
            date_range: One of "lifetime", "this_month", or "today"
            advertiser_id: Optional advertiser/company ID filter
            order_id: Optional order ID filter
            line_item_id: Optional line item ID filter
            requested_timezone: Timezone for the request (data will be converted if different)
            
        Returns:
            ReportingData object containing results and metadata
        """
        # Determine the appropriate dimensions and date range
        dimensions, start_date, end_date, granularity = self._get_report_config(date_range, requested_timezone)
        
        # Build the report query
        report_job = self._build_report_query(
            dimensions, 
            start_date, 
            end_date,
            advertiser_id,
            order_id,
            line_item_id
        )
        
        # Run the report
        report_data = self._run_report(report_job)
        
        # Calculate data freshness
        data_valid_until = self._calculate_data_freshness(date_range, requested_timezone)
        
        # Process and aggregate the data
        processed_data = self._process_report_data(
            report_data, 
            granularity,
            requested_timezone
        )
        
        # Calculate summary metrics
        metrics = self._calculate_metrics(processed_data)
        
        return ReportingData(
            data=processed_data,
            start_date=start_date,
            end_date=end_date,
            requested_timezone=requested_timezone,
            data_timezone=self.network_timezone if self.network_timezone != requested_timezone else requested_timezone,
            data_valid_until=data_valid_until,
            query_type=date_range,
            dimensions=dimensions,
            metrics=metrics
        )
    
    def _get_report_config(self, date_range: str, requested_tz: str) -> tuple:
        """Get the appropriate dimensions and date range for the report type"""
        tz = pytz.timezone(requested_tz)
        now = datetime.now(tz)
        
        # Base dimensions for all reports - simplified for compatibility with AD_SERVER metrics
        # Note: Including too many dimensions causes "COLUMNS_NOT_SUPPORTED_FOR_REQUESTED_DIMENSIONS" errors
        base_dimensions = ['ADVERTISER_ID', 'ORDER_ID', 'LINE_ITEM_ID']
        
        if date_range == "today":
            # Today by hour - need both DATE and HOUR dimensions for hourly reporting
            dimensions = ['DATE', 'HOUR'] + base_dimensions
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            granularity = "hourly"
        elif date_range == "this_month":
            # This month by day
            dimensions = ['DATE'] + base_dimensions
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            granularity = "daily"
        else:  # lifetime
            # Lifetime by day - limited to 90 days to avoid huge datasets
            dimensions = ['DATE'] + base_dimensions
            # Start from 90 days ago for manageable data volume
            start_date = (now - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            granularity = "daily"
        
        return dimensions, start_date, end_date, granularity
    
    def _build_report_query(
        self,
        dimensions: List[str],
        start_date: datetime,
        end_date: datetime,
        advertiser_id: Optional[str] = None,
        order_id: Optional[str] = None,
        line_item_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build the GAM report query"""
        
        # Build the WHERE clause and bind variables for ReportQuery
        # Note: We don't use StatementBuilder here because it adds LIMIT which is not supported in ReportService
        where_clauses = []
        bind_variables = []
        
        if advertiser_id:
            # Validate numeric ID
            try:
                advertiser_id_int = int(advertiser_id)
                where_clauses.append('ADVERTISER_ID = :advertiserId')
                bind_variables.append({'key': 'advertiserId', 'value': {'value': str(advertiser_id_int), 'xsi_type': 'NumberValue'}})
            except (ValueError, TypeError):
                logger.warning(f"Invalid advertiser_id format: {advertiser_id}")
        
        if order_id:
            # Validate numeric ID
            try:
                order_id_int = int(order_id)
                where_clauses.append('ORDER_ID = :orderId')
                bind_variables.append({'key': 'orderId', 'value': {'value': str(order_id_int), 'xsi_type': 'NumberValue'}})
            except (ValueError, TypeError):
                logger.warning(f"Invalid order_id format: {order_id}")
        
        if line_item_id:
            # Validate numeric ID
            try:
                line_item_id_int = int(line_item_id)
                where_clauses.append('LINE_ITEM_ID = :lineItemId')
                bind_variables.append({'key': 'lineItemId', 'value': {'value': str(line_item_id_int), 'xsi_type': 'NumberValue'}})
            except (ValueError, TypeError):
                logger.warning(f"Invalid line_item_id format: {line_item_id}")
        
        # NOTE: We cannot filter by AD_SERVER_IMPRESSIONS in the WHERE clause
        # as it's not a filterable field in GAM's PQL. We'll filter during processing instead.
        
        report_job = {
            'reportQuery': {
                'dimensions': dimensions,
                'columns': [
                    'AD_SERVER_IMPRESSIONS',
                    'AD_SERVER_CLICKS',
                    'AD_SERVER_CPM_AND_CPC_REVENUE'  # Revenue/spend - this is always available
                ],
                'dateRangeType': 'CUSTOM_DATE',
                'startDate': {
                    'year': start_date.year,
                    'month': start_date.month,
                    'day': start_date.day
                },
                'endDate': {
                    'year': end_date.year,
                    'month': end_date.month,
                    'day': end_date.day
                },
                'timeZoneType': 'PUBLISHER',  # Use publisher's timezone
                'statement': {
                    'query': 'WHERE ' + ' AND '.join(where_clauses),
                    'values': bind_variables if bind_variables else None
                } if where_clauses else None
            }
        }
        
        return report_job
    
    def _run_report(self, report_job: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run the report and return the data"""
        try:
            # Start the report job - returns a ReportJob object with an 'id' field
            report_job_response = self.report_service.runReportJob(report_job)
            
            # Extract the report job ID from the response
            if hasattr(report_job_response, 'id'):
                report_job_id = report_job_response.id
            elif isinstance(report_job_response, dict) and 'id' in report_job_response:
                report_job_id = report_job_response['id']
            else:
                # If it's already just the ID
                report_job_id = report_job_response
            
            logger.info(f"Started GAM report job with ID: {report_job_id}")
            
            # Wait for completion
            max_wait = 300  # 5 minutes maximum
            wait_time = 0
            while wait_time < max_wait:
                status = self.report_service.getReportJobStatus(report_job_id)
                if status == 'COMPLETED':
                    break
                elif status == 'FAILED':
                    raise Exception(f"GAM report job failed")
                time.sleep(2)
                wait_time += 2
            
            if self.report_service.getReportJobStatus(report_job_id) != 'COMPLETED':
                raise Exception(f"GAM report job timed out after {max_wait} seconds")
            
            # Download the report with proper cleanup
            tmp_file_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.csv.gz', delete=False) as tmp_file:
                    self.report_downloader.DownloadReportToFile(
                        report_job_id, 'CSV_DUMP', tmp_file
                    )
                    tmp_file_path = tmp_file.name
                
                # Parse the CSV data
                with gzip.open(tmp_file_path, 'rt') as gz_file:
                    csv_reader = csv.DictReader(gz_file)
                    data = list(csv_reader)
                
                # Debug: Log the first row to see column names
                if data:
                    logger.info(f"CSV columns: {list(data[0].keys())}")
                    logger.info(f"First row sample: {data[0]}")
                    logger.info(f"Total rows in report: {len(data)}")
                else:
                    logger.warning("GAM report returned no data rows")
                
                return data
            finally:
                # Always clean up temp file
                if tmp_file_path:
                    try:
                        import os
                        os.unlink(tmp_file_path)
                    except Exception as e:
                        logger.warning(f"Failed to clean up temp file {tmp_file_path}: {e}")
            
        except Exception as e:
            raise Exception(f"Error running GAM report: {str(e)}")
    
    def _process_report_data(
        self, 
        raw_data: List[Dict[str, Any]], 
        granularity: str,
        requested_tz: str
    ) -> List[Dict[str, Any]]:
        """Process and aggregate the raw report data"""
        
        # Map possible CSV column names to our field names
        # GAM CSV might use different names than the API constants
        column_mappings = {
            # Dimensions - only the ones we're actually using
            'Dimension.ADVERTISER_ID': 'ADVERTISER_ID',
            'Dimension.ORDER_ID': 'ORDER_ID',
            'Dimension.LINE_ITEM_ID': 'LINE_ITEM_ID',
            'Dimension.DATE': 'DATE',
            'Dimension.HOUR': 'HOUR',
            # Metrics - only including the ones we're actually requesting
            'Column.AD_SERVER_IMPRESSIONS': 'AD_SERVER_IMPRESSIONS',
            'Column.AD_SERVER_CLICKS': 'AD_SERVER_CLICKS',
            'Column.AD_SERVER_CPM_AND_CPC_REVENUE': 'AD_SERVER_CPM_AND_CPC_REVENUE',
        }
        
        # Dictionary to store aggregated data
        # Key will be a tuple of dimension values
        aggregated_data = {}
        
        for row in raw_data:
            # Normalize column names
            normalized_row = {}
            for key, value in row.items():
                # Check if it's a GAM CSV column name
                if key in column_mappings:
                    normalized_row[column_mappings[key]] = value
                else:
                    # Use as-is
                    normalized_row[key] = value
            
            # Skip rows with zero impressions to reduce data volume
            impressions = int(normalized_row.get('AD_SERVER_IMPRESSIONS', 0) or 0)
            if impressions == 0:
                continue
            
            # Build aggregation key from dimensions
            # Include timestamp for time-based aggregation
            timestamp = self._parse_timestamp(normalized_row, granularity)
            
            agg_key = (
                timestamp,
                normalized_row.get('ADVERTISER_ID', ''),
                normalized_row.get('ORDER_ID', ''),
                normalized_row.get('LINE_ITEM_ID', '')
            )
            
            # Initialize or update aggregated metrics
            if agg_key not in aggregated_data:
                aggregated_data[agg_key] = {
                    'timestamp': timestamp,
                    'advertiser_id': normalized_row.get('ADVERTISER_ID', ''),
                    'advertiser_name': normalized_row.get('ADVERTISER_NAME', ''),
                    'order_id': normalized_row.get('ORDER_ID', ''),
                    'order_name': normalized_row.get('ORDER_NAME', ''),
                    'line_item_id': normalized_row.get('LINE_ITEM_ID', ''),
                    'line_item_name': normalized_row.get('LINE_ITEM_NAME', ''),
                    'impressions': 0,
                    'clicks': 0,
                    'revenue_micros': 0,  # Keep in micros for accurate summing
                    'row_count': 0  # Track number of rows aggregated
                }
            
            # Aggregate metrics
            agg = aggregated_data[agg_key]
            agg['impressions'] += int(normalized_row.get('AD_SERVER_IMPRESSIONS', 0) or 0)
            agg['clicks'] += int(normalized_row.get('AD_SERVER_CLICKS', 0) or 0)
            agg['revenue_micros'] += float(normalized_row.get('AD_SERVER_CPM_AND_CPC_REVENUE', 0) or 0)
            agg['row_count'] += 1
        
        # Convert aggregated data to list and calculate derived metrics
        processed = []
        for agg_data in aggregated_data.values():
            # Convert revenue from micros to dollars
            spend = agg_data['revenue_micros'] / 1_000_000
            
            # Calculate derived metrics
            impressions = agg_data['impressions']
            clicks = agg_data['clicks']
            
            # Calculate CTR (clicks/impressions as percentage)
            ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
            
            # Calculate CPM (cost per thousand impressions)
            cpm = (spend / impressions * 1000) if impressions > 0 else 0.0
            
            processed_row = {
                'timestamp': agg_data['timestamp'],
                'advertiser_id': agg_data['advertiser_id'],
                'advertiser_name': agg_data.get('advertiser_name', ''),
                'order_id': agg_data['order_id'],
                'order_name': agg_data.get('order_name', ''),
                'line_item_id': agg_data['line_item_id'],
                'line_item_name': agg_data.get('line_item_name', ''),
                'impressions': impressions,
                'clicks': clicks,
                'ctr': round(ctr, 4),
                'spend': round(spend, 2),
                'cpm': round(cpm, 2),  # Changed from ecpm to cpm for clarity
                'aggregated_rows': agg_data['row_count']  # Useful for debugging
            }
            
            processed.append(processed_row)
        
        # Sort by timestamp and then by spend (descending)
        processed.sort(key=lambda x: (x['timestamp'], -x['spend']))
        
        # Log aggregation results
        logger.info(f"Aggregated {len(raw_data)} raw rows into {len(processed)} aggregated rows")
        
        return processed
    
    def _parse_timestamp(self, row: Dict[str, Any], granularity: str) -> str:
        """Parse timestamp from row based on granularity"""
        if granularity == "hourly":
            # HOUR dimension returns values 0-23 according to documentation
            # Combined with DATE for full timestamp
            date = row.get('DATE', '')
            hour = row.get('HOUR', '0')
            if date:
                # Combine DATE (YYYY-MM-DD) with HOUR (0-23)
                try:
                    hour_val = int(hour)
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    dt = dt.replace(hour=hour_val)
                    return dt.isoformat()
                except (ValueError, TypeError):
                    # Fallback for unexpected format
                    return f"{date}T{hour:02d}:00:00"
        else:  # daily
            # DATE dimension uses ISO 8601 format 'YYYY-MM-DD'
            date = row.get('DATE', '')
            if date:
                return f"{date}T00:00:00"
        
        return ""
    
    def _calculate_data_freshness(self, date_range: str, requested_tz: str) -> datetime:
        """
        Calculate when the data is valid until based on GAM's reporting delays
        
        According to Google documentation:
        - Most data is available within 4 hours
        - Previous month's data is frozen after 3 AM Pacific Time on the first day of every month
        """
        tz = pytz.timezone(requested_tz)
        now = datetime.now(tz)
        
        # GAM data typically has a 4-hour delay
        four_hours_ago = now - timedelta(hours=4)
        
        if date_range == "today":
            # For hourly data, be conservative and assume 4-hour delay
            # Round down to the last completed hour
            data_valid_until = four_hours_ago.replace(minute=0, second=0, microsecond=0)
        elif date_range == "this_month":
            # Daily data has the same 4-hour delay
            # If we're early in the day, yesterday's data might not be complete
            if now.hour < 7:  # Account for 4-hour delay + 3 AM PT freeze time
                # Data is valid through 2 days ago
                data_valid_until = (now - timedelta(days=2)).replace(hour=23, minute=59, second=59)
            else:
                # Yesterday's data should be complete
                data_valid_until = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59)
        else:  # lifetime
            # Same as this_month for the most recent data
            if now.hour < 7:
                data_valid_until = (now - timedelta(days=2)).replace(hour=23, minute=59, second=59)
            else:
                data_valid_until = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59)
        
        return data_valid_until
    
    def _calculate_metrics(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary metrics from the processed data"""
        if not data:
            return {
                'total_impressions': 0,
                'total_clicks': 0,
                'total_spend': 0.0,
                'average_ctr': 0.0,
                'average_ecpm': 0.0,
                'total_video_completions': 0,
                'unique_advertisers': 0,
                'unique_orders': 0,
                'unique_line_items': 0
            }
        
        total_impressions = sum(row['impressions'] for row in data)
        total_clicks = sum(row['clicks'] for row in data)
        total_spend = sum(row['spend'] for row in data)
        
        # Calculate averages
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0
        avg_ecpm = (total_spend / total_impressions * 1000) if total_impressions > 0 else 0.0
        
        # Count unique entities
        unique_advertisers = len(set(row['advertiser_id'] for row in data if row['advertiser_id']))
        unique_orders = len(set(row['order_id'] for row in data if row['order_id']))
        unique_line_items = len(set(row['line_item_id'] for row in data if row['line_item_id']))
        
        return {
            'total_impressions': total_impressions,
            'total_clicks': total_clicks,
            'total_spend': round(total_spend, 2),
            'average_ctr': round(avg_ctr, 4),
            'average_ecpm': round(avg_ecpm, 2),
            'unique_advertisers': unique_advertisers,
            'unique_orders': unique_orders,
            'unique_line_items': unique_line_items
        }
    
    def get_advertiser_summary(
        self,
        advertiser_id: str,
        date_range: Literal["lifetime", "this_month", "today"],
        requested_timezone: str = "America/New_York"
    ) -> Dict[str, Any]:
        """
        Get a summary of all orders and line items for an advertiser
        
        Returns aggregated data by order and line item
        """
        report_data = self.get_reporting_data(
            date_range=date_range,
            advertiser_id=advertiser_id,
            requested_timezone=requested_timezone
        )
        
        # Aggregate by order and line item
        order_summary = {}
        line_item_summary = {}
        
        for row in report_data.data:
            order_id = row['order_id']
            line_item_id = row['line_item_id']
            
            # Aggregate by order
            if order_id not in order_summary:
                order_summary[order_id] = {
                    'order_id': order_id,
                    'order_name': row['order_name'],
                    'impressions': 0,
                    'clicks': 0,
                    'spend': 0.0,
                    'line_items': set()
                }
            
            order_summary[order_id]['impressions'] += row['impressions']
            order_summary[order_id]['clicks'] += row['clicks']
            order_summary[order_id]['spend'] += row['spend']
            order_summary[order_id]['line_items'].add(line_item_id)
            
            # Aggregate by line item
            if line_item_id not in line_item_summary:
                line_item_summary[line_item_id] = {
                    'line_item_id': line_item_id,
                    'line_item_name': row['line_item_name'],
                    'order_id': order_id,
                    'order_name': row['order_name'],
                    'impressions': 0,
                    'clicks': 0,
                    'spend': 0.0
                }
            
            line_item_summary[line_item_id]['impressions'] += row['impressions']
            line_item_summary[line_item_id]['clicks'] += row['clicks']
            line_item_summary[line_item_id]['spend'] += row['spend']
        
        # Convert sets to counts
        for order in order_summary.values():
            order['line_item_count'] = len(order['line_items'])
            del order['line_items']
        
        return {
            'advertiser_id': advertiser_id,
            'date_range': date_range,
            'data_valid_until': report_data.data_valid_until.isoformat(),
            'timezone': report_data.data_timezone,
            'metrics': report_data.metrics,
            'orders': list(order_summary.values()),
            'line_items': list(line_item_summary.values())
        }