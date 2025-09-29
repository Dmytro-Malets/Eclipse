import aiohttp, pytz, logging
from typing import Optional, Dict, Any
from datetime import datetime
from .customerror import NoAPIError
from config.settings import GOOGLE_API_KEY

logger = logging.getLogger(__name__)


class LocationService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GOOGLE_API_KEY
        if not self.api_key:
            raise NoAPIError(
                "Google Maps API key is required. Set GOOGLE_API_KEY environment variable or pass api_key parameter.")

        self.geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json"
        self.timezone_url = "https://maps.googleapis.com/maps/api/timezone/json"

    async def geocode_location(self, location_name: str) -> Optional[Dict[str, Any]]:
        params = {
            'address': location_name,
            'key': self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.geocoding_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Google Geocoding API HTTP error: {response.status}")
                        return None

                    data = await response.json()

                    if data['status'] != 'OK':
                        logger.error(f"Google Geocoding API error: {data['status']}")
                        if data['status'] == 'ZERO_RESULTS':
                            logger.info(f"Location not found: {location_name}")
                        return None

                    if not data['results']:
                        logger.info(f"No results for location: {location_name}")
                        return None

                    result = data['results'][0]
                    location = result['geometry']['location']

                    # Extract location components
                    address_components = result.get('address_components', [])
                    country = ''
                    locality = ''

                    for component in address_components:
                        types = component.get('types', [])
                        if 'country' in types:
                            country = component.get('long_name', '')
                        elif 'locality' in types:
                            locality = component.get('long_name', '')
                        elif 'administrative_area_level_1' in types and not locality:
                            locality = component.get('long_name', '')

                    # Use locality as main name, fallback to formatted address first part
                    if not locality:
                        formatted_parts = result['formatted_address'].split(',')
                        locality = formatted_parts[0].strip() if formatted_parts else location_name

                    return {
                        'name': locality,
                        'full_name': result['formatted_address'],
                        'latitude': float(location['lat']),
                        'longitude': float(location['lng']),
                        'country': country,
                        'place_id': result.get('place_id', '')
                    }

        except Exception as e:
            logger.error(f"Error geocoding location {location_name}: {e}")
            return None

    async def reverse_geocode(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        params = {
            'latlng': f"{latitude},{longitude}",
            'key': self.api_key,
            'result_type': 'locality|administrative_area_level_1|country'  # Prioritize city-level results
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.geocoding_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Google Reverse Geocoding API HTTP error: {response.status}")
                        return None

                    data = await response.json()

                    if data['status'] != 'OK':
                        logger.error(f"Google Reverse Geocoding API error: {data['status']}")
                        return None

                    if not data['results']:
                        logger.info(f"No results for coordinates: {latitude}, {longitude}")
                        return None

                    result = data['results'][0]

                    # Extract location components
                    address_components = result.get('address_components', [])
                    country = ''
                    locality = ''

                    for component in address_components:
                        types = component.get('types', [])
                        if 'country' in types:
                            country = component.get('long_name', '')
                        elif 'locality' in types:
                            locality = component.get('long_name', '')
                        elif 'administrative_area_level_1' in types and not locality:
                            locality = component.get('long_name', '')

                    # Use locality as main name, fallback to formatted address first part
                    if not locality:
                        formatted_parts = result['formatted_address'].split(',')
                        locality = formatted_parts[0].strip() if formatted_parts else f"{latitude:.2f}, {longitude:.2f}"

                    return {
                        'name': locality,
                        'full_name': result['formatted_address'],
                        'latitude': latitude,
                        'longitude': longitude,
                        'country': country,
                        'place_id': result.get('place_id', '')
                    }

        except Exception as e:
            logger.error(f"Error reverse geocoding coordinates {latitude}, {longitude}: {e}")
            return None

    async def get_timezone(self, latitude: float, longitude: float, timestamp: Optional[int] = None) -> Optional[str]:

        if timestamp is None:
            timestamp = int(datetime.now().timestamp())

        params = {
            'location': f"{latitude},{longitude}",
            'timestamp': timestamp,
            'key': self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.timezone_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Google Timezone API HTTP error: {response.status}")
                        return None

                    data = await response.json()

                    if data['status'] != 'OK':
                        logger.error(f"Google Timezone API error: {data['status']}")
                        return None

                    return data.get('timeZoneId')

        except Exception as e:
            logger.error(f"Error getting timezone for {latitude}, {longitude}: {e}")
            return None

    @staticmethod
    def get_current_time(timezone_str: str) -> Optional[Dict[str, str]]:
        try:
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)

            return {
                'time': now.strftime('%H:%M:%S'),
                'date': now.strftime('%Y-%m-%d'),
                'datetime': now.strftime('%Y-%m-%d %H:%M:%S'),
                'timezone_abbr': now.strftime('%Z'),
                'utc_offset': now.strftime('%z')
            }
        except Exception as e:
            logger.error(f"Error getting current time for timezone {timezone_str}: {e}")
            return None

    @staticmethod
    def _generate_location_name(latitude: float) -> str:
        abs_lat = abs(latitude)
        # Polar regions
        if abs_lat > 66.5:
            if latitude > 0:
                return "Arctic Region"
            else:
                return "Antarctic Region"

        region_name = "Remote Area"
        return region_name

    @staticmethod
    def _calculate_timezone_from_longitude(latitude: float, longitude: float) -> str:
        # Line Islands (Kiribati) - UTC+14
        if -160 <= longitude <= -150 and -5 <= latitude <= 5:
            return "Pacific/Kiritimati"
        # Samoa - UTC+13
        if -173 <= longitude <= -171 and -15 <= latitude <= -13:
            return "Pacific/Apia"
        # Tonga - UTC+13
        if -176 <= longitude <= -173 and -22 <= latitude <= -15:
            return "Pacific/Tongatapu"

        offset_hours = round(longitude / 15)

        # POSIX convention: Etc/GMT uses inverted signs
        if offset_hours >= 0:
            return f"Etc/GMT-{offset_hours}"
        else:
            return f"Etc/GMT+{-offset_hours}"

    async def process_location(self, location_name: str) -> Optional[Dict[str, Any]]:

        # Step 1: Geocode the location
        location_data = await self.geocode_location(location_name)
        if not location_data:
            return None

        # Step 2: Get timezone
        timezone_str = await self.get_timezone(location_data['latitude'], location_data['longitude'])
        if not timezone_str:
            logger.warning(f"Could not determine timezone for {location_name}")
            return None

        # Step 3: Get current time
        time_data = self.get_current_time(timezone_str)
        if not time_data:
            logger.warning(f"Could not get current time for {timezone_str}")
            return None

        # Combine all data
        result = {
            **location_data,
            'timezone': timezone_str,
            'current_time': time_data
        }

        logger.info(f"📍 Successfully processed location: {location_name} -> {result['name']}")
        return result

    async def process_location_by_coordinates(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:

        # Step 1: Get timezone
        timezone_str = await self.get_timezone(latitude, longitude)
        if not timezone_str:
            logger.warning(f"Could not determine timezone for coordinates {latitude}, {longitude}")
            timezone_str = self._calculate_timezone_from_longitude(latitude, longitude)

        # Step 2: Get current time
        time_data = self.get_current_time(timezone_str)
        if not time_data:
            logger.warning(f"Could not get current time for {timezone_str}")
            return None

        # Step 3: Try to get location name via reverse geocoding
        location_data = await self.reverse_geocode(latitude, longitude)

        # If reverse geocoding failed or returned very generic result, use custom name
        if location_data:
            name = location_data['name']
            full_name = location_data['full_name']
            country = location_data.get('country', '')
        else:
            # Fallback for remote/unknown locations
            name = self._generate_location_name(latitude)
            full_name = f"{name} ({latitude:.4f} lat, {longitude:.4f} lon)"
            country = ''

        # Combine all data
        result = {
            'name': name,
            'full_name': full_name,
            'latitude': latitude,
            'longitude': longitude,
            'country': country,
            'timezone': timezone_str,
            'current_time': time_data,
            'place_id': location_data.get('place_id', '') if location_data else ''
        }

        logger.info(f"📍 Successfully processed coordinates: {latitude}, {longitude} -> {result['name']}")
        return result


location_service = LocationService()

def decimal_to_dms(decimal_deg: float, is_longitude: bool = False) -> str:
    """Convert decimal degrees to degrees, minutes, seconds format"""
    abs_deg = abs(decimal_deg)
    degrees = int(abs_deg)
    minutes = int((abs_deg - degrees) * 60)
    seconds = ((abs_deg - degrees) * 60 - minutes) * 60

    if is_longitude:
        direction = "E" if decimal_deg >= 0 else "W"
    else:
        direction = "N" if decimal_deg >= 0 else "S"

    return f"{degrees}°{minutes}'{seconds:.1f}\"{direction}"

def format_utc_offset(offset_str: str) -> str:
    """Convert +0300 format to GMT+3 format"""
    if not offset_str or len(offset_str) != 5:
        return offset_str

    sign = offset_str[0]
    hours = int(offset_str[1:3])
    minutes = int(offset_str[3:5])

    if minutes == 0:
        return f"GMT{sign}{hours}"
    else:
        return f"GMT{sign}{hours}:{minutes:02d}"