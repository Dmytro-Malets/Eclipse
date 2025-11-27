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

                    main_data = data.get('main', {})
                    temp_c = main_data.get('temp')
                    pressure_mbar = main_data.get('grnd_level') or main_data.get('pressure')

                    if cloud_cover is not None and temp_c is not None and pressure_mbar is not None:
                        return {
                            'cloud_cover': cloud_cover,
                            'temp_c': temp_c,
                            'pressure_mbar': pressure_mbar
                        }
                    else:
                        logger.warning("Cloud data not found in OpenWeatherMap response.")
                        return None

        except Exception as e:
            logger.error(f"Error fetching OpenWeatherMap data: {e}")
            return None


weather_api_service = WeatherAPIService()

def get_temp_pressure_conditions(weather_data: Dict[str, Any] | None) -> Dict[str, Any]:
    temp_default = 15.0
    pressure_default = 1030.0

    if weather_data and 'temp_c' in weather_data and 'pressure_mbar' in weather_data:
        temp = float(weather_data['temp_c'])
        pressure = float(weather_data['pressure_mbar'])
    else:
        temp = temp_default
        pressure = pressure_default

    return {'temperature_C': temp, 'pressure_mbar': pressure}