import aiohttp, logging, pytz
from datetime import datetime
from typing import Dict, Any
from database.models import User

logger = logging.getLogger(__name__)


class UVService:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_uv_index(self, user: User) -> Dict[str, Any] | None:

        if not user.has_location:
            return None

        params = {
            'latitude': user.latitude,
            'longitude': user.longitude,
            'hourly': 'uv_index',
            'timezone': user.timezone,
            'forecast_days': 1
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    response.raise_for_status()  # Will throw an error for 4xx/5xx statuses
                    data = await response.json()

                    user_tz = pytz.timezone(user.timezone)
                    now = datetime.now(user_tz)

                    # Format the time for searching in the Open-Meteo data array
                    # Example of the format in the API: "2025-09-25T20:00"
                    current_hour_str = now.strftime('%Y-%m-%dT%H:00')

                    # Find the index of the current hour in the time array
                    try:
                        hourly_data = data['hourly']
                        time_list = hourly_data['time']
                        uv_list = hourly_data['uv_index']

                        current_index = time_list.index(current_hour_str)
                        uv_value = uv_list[current_index]

                        if uv_value is None:
                            logger.warning(f"UV index is null for {current_hour_str} at {user.city}")
                            return None

                        return {
                            'uv_index': round(uv_value, 1),
                            'color': self._get_uv_color(uv_value)
                        }

                    except (ValueError, KeyError, IndexError) as e:
                        logger.error(f"Could not parse UV data for user {user.user_id}: {e}")
                        return None

        except aiohttp.ClientError as e:
            logger.error(f"AIOHttp error getting UV index from Open-Meteo: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting UV index: {e}")
            return None

    @staticmethod
    def _get_uv_color(uv_value: float) -> str:
        if uv_value < 3:
            return "🟢 Low"  # Green
        elif uv_value < 6:
            return "🟡 Moderate"  # Yellow
        elif uv_value < 8:
            return "🟠 High"  # Orange
        elif uv_value < 11:
            return "🔴 Very High"  # Red
        else:
            return "🟣 Extreme"  # Purple