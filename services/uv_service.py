import aiohttp, logging
from typing import Optional, Dict, Any
from database.models import User
from config.settings import OPENWEATHER_API_KEY
from .customerror import NoAPIError

logger = logging.getLogger(__name__)


class UVService:
    def __init__(self, api_key: str):
        self.api_key = api_key or OPENWEATHER_API_KEY
        if not self.api_key:
            raise NoAPIError(
                "Openweathermap API key is required. "
                "Set OPENWEATHER_API_KEY environment variable or pass api_key parameter.")

        self.base_url = "https://api.openweathermap.org/data/2.5/uvi"

    async def get_uv_index(self, user: User) -> Optional[Dict[str, Any]]:
        if not user.has_location:
            return None

        params = {
            'lat': user.latitude,
            'lon': user.longitude,
            'appid': self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"OpenWeatherMap UV API error: {response.status}")
                        return None

                    data = await response.json()
                    uv_value = data.get('value', 0)

                    return {
                        'uv_index': round(uv_value, 1),
                        'color': self._get_uv_color(uv_value)
                    }

        except Exception as e:
            logger.error(f"Error getting UV index: {e}")
            return None

    @staticmethod
    def _get_uv_color(uv_value: float) -> str:
        if uv_value < 3:
            return "🟢"  # Green
        elif uv_value < 6:
            return "🟡"  # Yellow
        elif uv_value < 8:
            return "🟠"  # Orange
        elif uv_value < 11:
            return "🔴"  # Red
        else:
            return "🟣"  # Purple