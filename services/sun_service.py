import logging, pytz
from datetime import datetime, date
from typing import Dict, Any, Optional
from astral import LocationInfo
from astral.sun import sun, azimuth, elevation
from database.models import User
from .uv_service import UVService
from config.settings import OPENWEATHER_API_KEY

logger = logging.getLogger(__name__)


class SunService:
    def __init__(self):
        self.uv_service = UVService(OPENWEATHER_API_KEY) if OPENWEATHER_API_KEY else None

    @staticmethod
    def create_location_info(user: User) -> Optional[LocationInfo]:
        if not user.has_location:
            return None

        try:
            location = LocationInfo(
                name=user.city,
                region="",  # Can be empty
                timezone=user.timezone,
                latitude=user.latitude,
                longitude=user.longitude
            )
            return location
        except Exception as e:
            logger.error(f"Error creating LocationInfo for user {user.user_id}: {e}")
            return None

    async def get_sun_times(self, user: User, target_date: date = None) -> Optional[Dict[str, Any]]:
        location = self.create_location_info(user)
        if not location:
            return None

        tz = pytz.timezone(user.timezone)
        now = datetime.now(tz)
        user_today = now.date()

        if target_date is None:
            target_date = user_today

        try:
            sun_times = sun(location.observer, date=target_date, tzinfo=tz)

            # Calculate current sun position if it's today for the user
            sun_position = None
            if target_date == user_today:
                sun_azimuth = azimuth(location.observer, now)
                sun_elevation = elevation(location.observer, now)
                sun_position = {
                    'azimuth': round(sun_azimuth, 1),
                    'elevation': round(sun_elevation, 1),
                    'is_up': sun_elevation > 0
                }

            # Get UV index
            uv_data = None
            if target_date == user_today and self.uv_service:
                uv_data = await self.uv_service.get_uv_index(user)

            # Calculate day length
            day_length = sun_times['sunset'] - sun_times['sunrise']
            day_length_formatted = self._format_duration(day_length)

            # Determine sun status
            sun_status = None
            if target_date == user_today:
                sun_status = self._determine_sun_status(now, sun_times)

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'date': target_date.strftime('%Y-%m-%d'),
                'date_formatted': target_date.strftime('%A, %B %d, %Y'),
                'sunrise': sun_times['sunrise'].strftime('%H:%M:%S'),
                'sunset': sun_times['sunset'].strftime('%H:%M:%S'),
                'solar_noon': sun_times['noon'].strftime('%H:%M:%S'),
                'day_length': day_length_formatted,
                'sun_status': sun_status,
                'current_time': now.strftime('%H:%M:%S') if target_date == user_today else None
            }

            # Add current position if available
            if sun_position:
                result['current_position'] = sun_position # noqa

            # Add UV index if available
            if uv_data is not None:
                result['uv_data'] = uv_data # noqa

            return result

        except Exception as e:
            logger.error(f"Error calculating sun times for user {user.user_id}: {e}")
            return None

    @staticmethod
    def _format_duration(duration) -> str:
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or len(parts) == 0:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    @staticmethod
    def _format_time_until(time_delta) -> str:
        total_seconds = int(time_delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _determine_sun_status(now: datetime, sun_times: Dict) -> str:
        if now < sun_times['sunrise']:
            time_to_sunrise = sun_times['sunrise'] - now
            formatted_time = SunService._format_time_until(time_to_sunrise)
            return f"Sun rises in {formatted_time}"
        elif now < sun_times['sunset']:
            time_to_sunset = sun_times['sunset'] - now
            formatted_time = SunService._format_time_until(time_to_sunset)
            return f"Sun sets in {formatted_time}"
        else:
            return "Sun has set"

    @staticmethod
    def format_sun_info_message(sun_data: Dict[str, Any]) -> str:
        location_info = sun_data['location']

        message = f"<b>{location_info['city']}. {sun_data['date_formatted']}</b>\n"
        if sun_data['current_time']:
            message += f"\n<b>Current Time:</b> {sun_data['current_time']}\n\n"
        else:
            message += f"\n"
        message += f"🌅 <b>Sunrise:</b> {sun_data['sunrise']}\n"
        message += f"🌇 <b>Sunset:</b> {sun_data['sunset']}\n"
        message += f"☀️ <b>Solar Noon:</b> {sun_data['solar_noon']}\n"
        message += f"⏱ <b>Day Length:</b> {sun_data['day_length']}\n\n"

        if sun_data['current_time']:
            message += f"<b>{sun_data['sun_status']}</b>\n\n"

            if 'uv_data' in sun_data and sun_data['uv_data'] is not None:
                uv = sun_data['uv_data']
                message += f"<b>UV Index:</b> {uv['uv_index']} {uv['color']}\n\n"

            if 'current_position' in sun_data:
                pos = sun_data['current_position']
                status_icon = "☀️" if pos['is_up'] else "🌙"
                message += f"<b>Current Sun Position: {status_icon}</b>\n"
                message += f"• <b>Azimuth:</b> {pos['azimuth']}°\n"
                message += f"• <b>Elevation:</b> {pos['elevation']}°\n"
                message += f"• <b>Status:</b> {'Above horizon' if pos['is_up'] else 'Below horizon'}\n"

        return message


sun_service = SunService()

def get_user_today(user: User) -> date:
    try:
        tz = pytz.timezone(user.timezone)
        now = datetime.now(tz)
        return now.date()
    except Exception:
        return date.today()