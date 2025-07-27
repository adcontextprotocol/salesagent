"""Targeting utilities for validation, normalization, and platform mapping."""

import re
from typing import List, Dict, Any, Optional, Set
from schemas import Targeting, Dayparting, FrequencyCap, DaypartSchedule

class TargetingValidator:
    """Validates and normalizes targeting parameters."""
    
    # Valid geographic formats
    GEO_PATTERNS = {
        'country': re.compile(r'^[A-Z]{2}$'),  # US, CA, GB
        'state': re.compile(r'^[A-Z]{2}-[A-Z]{2}$'),  # US-CA, CA-ON
        'dma': re.compile(r'^DMA-\d+$'),  # DMA-501
        'city': re.compile(r'^city:.+$'),  # city:New York,NY
        'postal': re.compile(r'^postal:\S+$'),  # postal:10001
    }
    
    # Valid device types
    VALID_DEVICES = {'desktop', 'mobile', 'tablet', 'ctv', 'audio_player'}
    
    # Valid platforms
    VALID_PLATFORMS = {'ios', 'android', 'windows', 'macos', 'linux'}
    
    # Valid browsers
    VALID_BROWSERS = {'chrome', 'safari', 'firefox', 'edge', 'opera'}
    
    # Audio daypart presets
    AUDIO_PRESETS = {
        'drive_time_morning': {'days': [1,2,3,4,5], 'start_hour': 6, 'end_hour': 10},
        'drive_time_evening': {'days': [1,2,3,4,5], 'start_hour': 16, 'end_hour': 19},
        'midday': {'days': [1,2,3,4,5], 'start_hour': 10, 'end_hour': 15},
        'evening': {'days': [0,1,2,3,4,5,6], 'start_hour': 19, 'end_hour': 24},
        'overnight': {'days': [0,1,2,3,4,5,6], 'start_hour': 0, 'end_hour': 6},
        'weekend': {'days': [0,6], 'start_hour': 0, 'end_hour': 24},
    }
    
    @classmethod
    def validate_geography(cls, geo_list: List[str]) -> Dict[str, List[str]]:
        """Validate and categorize geographic targeting."""
        result = {
            'countries': [],
            'states': [],
            'dmas': [],
            'cities': [],
            'postal_codes': [],
            'invalid': []
        }
        
        for geo in geo_list:
            if cls.GEO_PATTERNS['country'].match(geo):
                result['countries'].append(geo)
            elif cls.GEO_PATTERNS['state'].match(geo):
                result['states'].append(geo)
            elif cls.GEO_PATTERNS['dma'].match(geo):
                result['dmas'].append(geo)
            elif cls.GEO_PATTERNS['city'].match(geo):
                result['cities'].append(geo[5:])  # Remove 'city:' prefix
            elif cls.GEO_PATTERNS['postal'].match(geo):
                result['postal_codes'].append(geo[7:])  # Remove 'postal:' prefix
            else:
                result['invalid'].append(geo)
        
        return result
    
    @classmethod
    def validate_devices(cls, devices: List[str]) -> tuple[List[str], List[str]]:
        """Validate device types and return valid/invalid lists."""
        valid = [d for d in devices if d in cls.VALID_DEVICES]
        invalid = [d for d in devices if d not in cls.VALID_DEVICES]
        return valid, invalid
    
    @classmethod
    def validate_platforms(cls, platforms: List[str]) -> tuple[List[str], List[str]]:
        """Validate platforms and return valid/invalid lists."""
        valid = [p for p in platforms if p in cls.VALID_PLATFORMS]
        invalid = [p for p in platforms if p not in cls.VALID_PLATFORMS]
        return valid, invalid
    
    @classmethod
    def validate_browsers(cls, browsers: List[str]) -> tuple[List[str], List[str]]:
        """Validate browsers and return valid/invalid lists."""
        valid = [b for b in browsers if b in cls.VALID_BROWSERS]
        invalid = [b for b in browsers if b not in cls.VALID_BROWSERS]
        return valid, invalid
    
    @classmethod
    def expand_daypart_presets(cls, dayparting: Dayparting) -> Dayparting:
        """Expand named presets into actual schedules."""
        if not dayparting.presets:
            return dayparting
        
        expanded_schedules = list(dayparting.schedules)
        
        for preset in dayparting.presets:
            if preset in cls.AUDIO_PRESETS:
                preset_data = cls.AUDIO_PRESETS[preset]
                schedule = DaypartSchedule(
                    days=preset_data['days'],
                    start_hour=preset_data['start_hour'],
                    end_hour=preset_data['end_hour'],
                    timezone=dayparting.timezone
                )
                expanded_schedules.append(schedule)
        
        return Dayparting(
            timezone=dayparting.timezone,
            schedules=expanded_schedules,
            presets=None  # Clear presets after expansion
        )
    
    @classmethod
    def validate_targeting(cls, targeting: Targeting) -> Dict[str, Any]:
        """Validate all targeting parameters and return issues."""
        issues = {}
        
        # Validate geography
        if targeting.geography:
            geo_validation = cls.validate_geography(targeting.geography)
            if geo_validation['invalid']:
                issues['invalid_geography'] = geo_validation['invalid']
        
        if targeting.geography_exclude:
            geo_exclude_validation = cls.validate_geography(targeting.geography_exclude)
            if geo_exclude_validation['invalid']:
                issues['invalid_geography_exclude'] = geo_exclude_validation['invalid']
        
        # Validate devices
        if targeting.device_types:
            valid, invalid = cls.validate_devices(targeting.device_types)
            if invalid:
                issues['invalid_devices'] = invalid
        
        # Validate platforms
        if targeting.platforms:
            valid, invalid = cls.validate_platforms(targeting.platforms)
            if invalid:
                issues['invalid_platforms'] = invalid
        
        # Validate browsers
        if targeting.browsers:
            valid, invalid = cls.validate_browsers(targeting.browsers)
            if invalid:
                issues['invalid_browsers'] = invalid
        
        # Validate dayparting
        if targeting.dayparting:
            for schedule in targeting.dayparting.schedules:
                if schedule.start_hour >= schedule.end_hour:
                    issues.setdefault('dayparting_errors', []).append(
                        f"Invalid schedule: start_hour ({schedule.start_hour}) must be less than end_hour ({schedule.end_hour})"
                    )
                if any(day < 0 or day > 6 for day in schedule.days):
                    issues.setdefault('dayparting_errors', []).append(
                        "Invalid days: must be between 0 (Sunday) and 6 (Saturday)"
                    )
        
        # Validate frequency cap
        if targeting.frequency_cap:
            if targeting.frequency_cap.impressions <= 0:
                issues['frequency_cap_error'] = "Impressions must be greater than 0"
        
        return issues


class TargetingMapper:
    """Maps AdCP targeting to platform-specific formats."""
    
    @staticmethod
    def to_gam_targeting(targeting: Targeting) -> Dict[str, Any]:
        """Convert AdCP targeting to Google Ad Manager format."""
        gam_targeting = {}
        
        # Geographic targeting
        if targeting.geography:
            geo_data = TargetingValidator.validate_geography(targeting.geography)
            # GAM requires specific geo IDs - this would need a lookup table
            # For now, we'll structure the data
            gam_targeting['geoTargeting'] = {
                'targetedLocations': [],
                'excludedLocations': []
            }
            # TODO: Implement geo ID lookup
        
        # Technology/Device targeting
        if targeting.device_types or targeting.platforms or targeting.browsers:
            tech_targeting = {}
            
            if targeting.device_types:
                # Map to GAM device categories
                device_map = {
                    'desktop': 'DESKTOP',
                    'mobile': 'MOBILE',
                    'tablet': 'TABLET',
                    'ctv': 'CONNECTED_TV'
                }
                tech_targeting['deviceCategories'] = [
                    device_map.get(d, d.upper()) for d in targeting.device_types
                ]
            
            if targeting.platforms:
                # Map to GAM operating systems
                os_map = {
                    'ios': 'IOS',
                    'android': 'ANDROID',
                    'windows': 'WINDOWS',
                    'macos': 'MAC_OS'
                }
                tech_targeting['operatingSystems'] = [
                    os_map.get(p, p.upper()) for p in targeting.platforms
                ]
            
            if targeting.browsers:
                # Map to GAM browsers
                browser_map = {
                    'chrome': 'CHROME',
                    'safari': 'SAFARI',
                    'firefox': 'FIREFOX',
                    'edge': 'EDGE'
                }
                tech_targeting['browsers'] = [
                    browser_map.get(b, b.upper()) for b in targeting.browsers
                ]
            
            gam_targeting['technologyTargeting'] = tech_targeting
        
        # Dayparting
        if targeting.dayparting:
            daypart_targeting = []
            expanded = TargetingValidator.expand_daypart_presets(targeting.dayparting)
            
            for schedule in expanded.schedules:
                daypart_targeting.append({
                    'dayOfWeek': [f'DAY_{d}' for d in schedule.days],
                    'startTime': {'hour': schedule.start_hour, 'minute': 0},
                    'endTime': {'hour': schedule.end_hour, 'minute': 0},
                    'timeZone': schedule.timezone or expanded.timezone
                })
            
            gam_targeting['dayPartTargeting'] = daypart_targeting
        
        # Custom key-value targeting
        if targeting.custom and 'key_values' in targeting.custom:
            gam_targeting['customTargeting'] = targeting.custom['key_values']
        
        return gam_targeting
    
    @staticmethod
    def to_kevel_targeting(targeting: Targeting) -> Dict[str, Any]:
        """Convert AdCP targeting to Kevel format."""
        kevel_targeting = {}
        
        # Geographic targeting
        if targeting.geography:
            geo_data = TargetingValidator.validate_geography(targeting.geography)
            kevel_targeting['geo'] = {
                'countries': geo_data['countries'],
                'regions': geo_data['states'],  # Kevel calls states "regions"
                'metros': [int(dma.replace('DMA-', '')) for dma in geo_data['dmas']],
                'cities': geo_data['cities']
            }
        
        # Device targeting (Kevel has limited device support)
        if targeting.device_types:
            device_map = {
                'desktop': 'desktop',
                'mobile': 'mobile',
                'tablet': 'tablet'
            }
            kevel_targeting['devices'] = [
                device_map.get(d) for d in targeting.device_types 
                if d in device_map
            ]
        
        # Keywords
        if targeting.keywords_include:
            kevel_targeting['keywords'] = targeting.keywords_include
        
        # Custom targeting
        if targeting.custom:
            if 'site_ids' in targeting.custom:
                kevel_targeting['siteIds'] = targeting.custom['site_ids']
            if 'zone_ids' in targeting.custom:
                kevel_targeting['zoneIds'] = targeting.custom['zone_ids']
        
        return kevel_targeting
    
    @staticmethod
    def to_triton_targeting(targeting: Targeting) -> Dict[str, Any]:
        """Convert AdCP targeting to Triton Digital format."""
        triton_targeting = {}
        
        # Geographic targeting (audio market focused)
        if targeting.geography:
            geo_data = TargetingValidator.validate_geography(targeting.geography)
            triton_targeting['targeting'] = {
                'countries': geo_data['countries'],
                'states': [state.split('-')[1] for state in geo_data['states']],  # Just state codes
                'markets': []  # Would need market name mapping
            }
        
        # Dayparting (special audio presets)
        if targeting.dayparting:
            if targeting.dayparting.presets:
                triton_targeting['dayparts'] = targeting.dayparting.presets
            else:
                # Convert schedules to Triton format
                daypart_names = []
                for schedule in targeting.dayparting.schedules:
                    # Map to closest preset if possible
                    if schedule.start_hour == 6 and schedule.end_hour == 10:
                        daypart_names.append('drive_time_morning')
                    elif schedule.start_hour == 16 and schedule.end_hour == 19:
                        daypart_names.append('drive_time_evening')
                    # Add more mappings as needed
                
                if daypart_names:
                    triton_targeting['dayparts'] = daypart_names
        
        # Audio-specific targeting
        if targeting.custom:
            if 'station_ids' in targeting.custom:
                triton_targeting['stationIds'] = targeting.custom['station_ids']
            if 'genres' in targeting.custom:
                triton_targeting['genres'] = targeting.custom['genres']
        
        return triton_targeting
    
    @staticmethod
    def check_platform_compatibility(targeting: Targeting, platform: str) -> Dict[str, Any]:
        """Check if targeting options are compatible with a platform."""
        compatibility = {
            'supported': [],
            'unsupported': [],
            'warnings': []
        }
        
        if platform == 'google_ad_manager':
            # GAM supports everything
            compatibility['supported'] = ['all_features']
            
        elif platform == 'kevel':
            # Kevel limitations
            if targeting.device_types:
                unsupported_devices = [d for d in targeting.device_types if d in ['ctv', 'audio_player']]
                if unsupported_devices:
                    compatibility['unsupported'].append(f"Device types: {unsupported_devices}")
            
            if targeting.frequency_cap and targeting.frequency_cap.per == 'household':
                compatibility['warnings'].append("Household-level frequency capping limited to IP-based")
            
        elif platform == 'triton_digital':
            # Triton limitations (audio only)
            if targeting.device_types:
                non_audio_devices = [d for d in targeting.device_types if d != 'audio_player']
                if non_audio_devices:
                    compatibility['unsupported'].append(f"Non-audio devices: {non_audio_devices}")
            
            if targeting.content_categories_include or targeting.content_categories_exclude:
                compatibility['warnings'].append("Content categories limited to audio genres")
        
        return compatibility