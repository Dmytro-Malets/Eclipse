import aiohttp, logging, pytz
from datetime import datetime, timedelta, tzinfo
from typing import Dict, Any, List
from database.models import User
from config.settings import N2YO_API_KEY
from .location_service import location_service

logger = logging.getLogger(__name__)


class ISSService:
    def __init__(self):
        self.base_url = "https://api.n2yo.com/rest/v1/satellite"
        self.iss_norad_id = "25544"  # NORAD ISS ID
        self.api_key = N2YO_API_KEY

    async def get_iss_data(self, user: User) -> Dict[str, Any] | None:
        if not user.has_location:
            return None

        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)

            # Get current ISS position relative to user location
            current_position = await self._get_current_position(user.latitude, user.longitude)

            # Get upcoming visible passes
            passes = await self._get_visual_passes(user.latitude, user.longitude, altitude = 0, days = 3, min_visibility_seconds = 0)

            current_position = {} if current_position is None else current_position

            iss_location_name = None
            if current_position and 'sat_latitude' in current_position:
                iss_location_name = await self._get_iss_location_name(current_position['sat_latitude'], current_position['sat_longitude'])

            formatted_passes = []
            if passes:
                formatted_passes = self._format_passes(passes, tz)

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'current_time': now.strftime('%H:%M:%S'),
                'date_formatted': now.strftime('%A, %B %d, %Y'),
                'current_position': current_position,
                'iss_location_name': iss_location_name,
                'passes': formatted_passes
            }

            return result

        except Exception as e:
            logger.error(f"Error getting ISS data for user {user.user_id}: {e}")
            return None

    async def _get_current_position(self, lat: float, lon: float) -> Dict[str, Any] | None:
        try:
            url = f"{self.base_url}/positions/{self.iss_norad_id}/{lat}/{lon}/0/1/"
            params = {'apiKey': self.api_key}

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"N2YO Position API error: {response.status}")
                        return None

                    data = await response.json()

                    if 'positions' not in data or not data['positions']:
                        return None

                    position = data['positions'][0]

                    azimuth = float(position.get('azimuth', 0))
                    altitude = float(position.get('elevation', 0))
                    ra = float(position.get('ra', 0))
                    dec = float(position.get('dec', 0))

                    if altitude < 0:
                        status = "Below horizon"
                    else:
                        status = "Above horizon"

                    direction = self._get_compass_direction(azimuth)

                    return {
                        'azimuth': azimuth,
                        'altitude': altitude,
                        'right_ascension': ra,
                        'declination': dec,
                        'direction': direction,
                        'status': status,
                        'sat_latitude': float(position.get('satlatitude', 0)),
                        'sat_longitude': float(position.get('satlongitude', 0)),
                        'sat_altitude_km': float(position.get('sataltitude', 0)),
                        'timestamp': position.get('timestamp', 0)
                    }

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error getting ISS position: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting ISS current position: {e}")
            return None

    @staticmethod
    async def _get_iss_location_name(lat: float, lon: float) -> str | None:
        try:
            location_data = await location_service.reverse_geocode(lat, lon)

            if location_data:
                # Return formatted location string
                name = location_data['name']
                country = location_data.get('country', '')

                if country and country != name:
                    return f"{name}, {country}"
                return name

            # Fallback for ocean/remote areas
            return location_service.generate_location_name(lat)

        except Exception as e:
            logger.error(f"Error getting ISS location name: {e}")
            return None

    async def _get_visual_passes(self, lat: float, lon: float, altitude: int = 0, days: int = 3, min_visibility_seconds: int = 0) -> List[Dict[str, Any]] | None:
        try:
            url = f"{self.base_url}/visualpasses/{self.iss_norad_id}/{lat}/{lon}/{altitude}/{days}/{min_visibility_seconds}/"
            params = {'apiKey': self.api_key}

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"N2YO Visual Passes API error: {response.status} - {error_text}")
                        return None

                    data = await response.json()

                    if 'passes' not in data:
                        logger.warning("No passes found in response")
                        return None

                    passes = data['passes'][:5]
                    return passes

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error getting ISS passes: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting ISS passes: {e}")
            return None

    @staticmethod
    def _format_passes(passes: List[Dict[str, Any]], tz: tzinfo) -> List[Dict[str, Any]]:
        formatted = []

        for pass_data in passes:
            start_utc = pass_data.get('startUTC', 0)
            duration = pass_data.get('duration', 0)
            max_elevation = pass_data.get('maxEl', 0)
            start_az = pass_data.get('startAz', 0)
            start_az_compass = pass_data.get('startAzCompass', 'N/A')
            end_az = pass_data.get('endAz', 0)
            end_az_compass = pass_data.get('endAzCompass', 'N/A')
            mag = pass_data.get('mag', 0)

            start_dt = datetime.fromtimestamp(start_utc, tz=pytz.utc).astimezone(tz)

            now = datetime.now(tz)
            time_diff = start_dt - now

            if 0 < time_diff.total_seconds() < 3600:
                time_desc = "Soon"
            elif start_dt.date() == now.date():
                if now.hour < 4 and start_dt.hour > 6:
                    time_desc = "This morning"
                else:
                    time_desc = "Today"
            elif start_dt.date() == (now + timedelta(days=1)).date():
                time_desc = "Tomorrow"
            else:
                time_desc = start_dt.strftime('%B %d')

            formatted.append({
                'risetime': start_dt,
                'duration': duration,
                'max_elevation': max_elevation,
                'start_azimuth': start_az,
                'start_direction': start_az_compass,
                'end_azimuth': end_az,
                'end_direction': end_az_compass,
                'brightness': mag,
                'time_desc': time_desc,
                'time_formatted': start_dt.strftime('%H:%M:%S')
            })

        return formatted

    @staticmethod
    def _format_duration(seconds: int) -> str:
        minutes = seconds // 60
        secs = seconds % 60

        return f"{minutes}m {secs}s"

    @staticmethod
    def _get_compass_direction(azimuth: float) -> str:
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                      'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        idx = int((azimuth + 11.25) / 22.5) % 16

        return directions[idx]

    def format_iss_message(self, iss_data: Dict[str, Any]) -> str:
        if not iss_data:
            return "<b>❌ Unable to load ISS data</b>\n\nPlease try again later."

        location_info = iss_data['location']
        passes = iss_data.get('passes', [])

        message = f"<b>{location_info['city']}. {iss_data['date_formatted']}</b>\n\n"
        message += f"<b>Current Time:</b> {iss_data['current_time']}\n\n"

        message += "<b>🛰 ISS - International Space Station</b>\n\n"

        if iss_data.get('current_position'):
            pos = iss_data['current_position']
            message += f"<b>Current Position:</b>\n"
            message += f"• <b>Azimuth:</b> {pos['azimuth']:.1f}° ({pos['direction']})\n"
            message += f"• <b>Altitude:</b> {pos['altitude']:.1f}°\n"
            message += f"• <b>Status:</b> {pos['status']}\n\n"

            km_altitude = pos['sat_altitude_km']
            miles_altitude = km_altitude * 0.621371

            message += f"ISS is {km_altitude:.0f} km ({miles_altitude:.0f} miles) above Earth\n"
            message += f"<b>Coordinates:</b> {pos['sat_latitude']:.2f}° (lat), {pos['sat_longitude']:.2f}° (lon)\n"
            if iss_data.get('iss_location_name'):
                message += f"<b>Above:</b> {iss_data['iss_location_name']}\n"
            message += "\n"

        if passes:
            message += f"<b>Next Visible Passes:</b>\n\n"

            for idx, pass_info in enumerate(passes, 1):
                duration_str = self._format_duration(pass_info['duration'])

                message += f"<b>{idx}. {pass_info['time_desc']} - {pass_info['time_formatted']}</b>\n"
                message += f"• Duration: {duration_str}\n"
                message += f"• Max altitude: {pass_info['max_elevation']:.0f}°\n"
                message += f"• Apparent Magnitude: {pass_info['brightness']:.1f}\n"
                message += f"• Appears: {pass_info['start_direction']} → Disappears: {pass_info['end_direction']}\n"

                if idx < len(passes):
                    message += "\n"
        else:
            message += "<b>No visible passes in the next 3 days</b>"

        return message


iss_service = ISSService()