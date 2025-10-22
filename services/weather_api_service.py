import logging, aiohttp
from typing import Dict, Any
from config.settings import WEATHER_API_KEY
from database.models import User

logger = logging.getLogger(__name__)


class WeatherAPIService:
    def __init__(self):
        self.weather_url = "https://api.openweathermap.org/data/2.5/weather"
        self.weather_api_key = WEATHER_API_KEY

    async def get_current_weather(self, user: User) -> Dict[str, Any] | None:
        if not self.weather_api_key:
            return None

        params = {
            'lat': user.latitude,
            'lon': user.longitude,
            'appid': self.weather_api_key,
            'units': 'metric'
        }

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.weather_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"OpenWeatherMap API error: {response.status} {await response.text()}")
                        return None

                    data = await response.json()

                    cloud_cover = data.get('clouds', {}).get('all')

                    if cloud_cover is not None:
                        return {'cloud_cover': cloud_cover}
                    else:
                        logger.warning("Cloud data not found in OpenWeatherMap response.")
                        return None

        except Exception as e:
            logger.error(f"Error fetching OpenWeatherMap data: {e}")
            return None


weather_api_service = WeatherAPIService()