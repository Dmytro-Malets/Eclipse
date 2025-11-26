import logging, pytz
import numpy as np
from datetime import datetime, date
from typing import Dict, Any, List
from skyfield.api import load, wgs84, Star
from skyfield.magnitudelib import planetary_magnitude
from database.models import User
from .weather_api_service import weather_api_service, get_temp_pressure_conditions
from .astro_utils import calculate_extended_refraction

logger = logging.getLogger(__name__)


class NightSkyService:
    def __init__(self):
        # Load ephemeris data
        self.ts = load.timescale()
        self.eph = load('de421.bsp') # NASA JPL ephemeris
        self.earth = self.eph['earth']
        self.sun = self.eph['sun']
        self.moon = self.eph['moon']

        self.planets = {
            'Mercury': self.eph['mercury'],
            'Venus': self.eph['venus'],
            'Mars': self.eph['mars'],
            'Jupiter': self.eph['jupiter barycenter'],
            'Saturn': self.eph['saturn barycenter'],
            'Uranus': self.eph['uranus barycenter'],
            'Neptune': self.eph['neptune barycenter']
        }

    async def get_night_sky_data(self, user: User, target_date: date = None) -> Dict[str, Any] | None:
        if not user.has_location:
            return None

        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)
            user_today = now.date()

            if target_date is None:
                target_date = user_today

            # Use current time if it's today, otherwise use midnight
            if target_date == user_today:
                target_datetime = now
            else:
                target_datetime = tz.localize(datetime.combine(target_date, datetime.min.time()))

            # Create observer location
            observer = self.earth + wgs84.latlon(user.latitude, user.longitude)

            # Convert to skyfield time
            t = self.ts.from_datetime(target_datetime.astimezone(pytz.utc))

            # Get weather data
            weather_data = None
            if target_date == user_today:
                weather_data = await weather_api_service.get_current_weather(user)

            # Get sun and moon positions
            sun_data = self._get_celestial_position(observer, t, self.sun, 'Sun', weather_data)
            moon_data = self._get_celestial_position(observer, t, self.moon, 'Moon', weather_data)

            # Check if it's nighttime
            is_night = sun_data['altitude'] < -6.0

            # Get visible planets
            visible_planets = self._get_visible_planets(observer, t, weather_data)

            # Get the brightest stars
            brightest_stars = self._get_brightest_stars(observer, t, weather_data)

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'time': target_datetime.strftime('%H:%M:%S'),
                'date_formatted': target_date.strftime('%A, %B %d, %Y'),
                'current_time': now.strftime('%H:%M:%S') if target_date == user_today else None,
                'is_night': is_night,
                'sun': sun_data,
                'moon': moon_data,
                'planets': visible_planets,
                'stars': brightest_stars,
                'sky_condition': self._get_sky_condition(sun_data['altitude']),
                'cloud_cover': weather_data.get('cloud_cover') if weather_data and target_date == user_today else None
            }

            return result

        except Exception as e:
            logger.error(f"Error calculating night sky data for user {user.user_id}: {e}")
            return None

    @staticmethod
    def _get_celestial_position(observer, t, body, name: str, weather_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        try:
            apparent = observer.at(t).observe(body).apparent()
            geom_alt, az, distance = apparent.altaz()

            # Extract weather conditions
            conditions = get_temp_pressure_conditions(weather_data)
            temp_c = conditions['temperature_C']
            pressure = conditions['pressure_mbar']

            apparent_alt_deg = calculate_extended_refraction(geom_alt.degrees, temp_c, pressure)

            if name in ('Sun', 'Moon'):
                is_visible = apparent_alt_deg > -(16.0 / 60.0)
            else:
                is_visible = apparent_alt_deg > 0.0

            return {
                'name': name,
                'altitude': round(apparent_alt_deg, 1),
                'azimuth': round(az.degrees, 1),
                'is_visible': is_visible,
                'distance_au': round(distance.au, 3) if hasattr(distance, 'au') else None
            }
        except Exception as e:
            logger.error(f"Error getting position for {name}: {e}")
            return {
                'name': name,
                'altitude': 0,
                'azimuth': 0,
                'is_visible': False,
                'distance_au': None
            }

    def _get_visible_planets(self, observer, t, weather_data: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        visible = []

        for name, planet in self.planets.items():
            position = self._get_celestial_position(observer, t, planet, name, weather_data)
            # Only include if above horizon
            if position['is_visible']:
                magnitude = self._calculate_planet_magnitude(t, planet, name)
                position['magnitude'] = magnitude if magnitude is not None else 'N/A'
                visible.append(position)

        # Sort by magnitude
        visible.sort(key=lambda x: x['magnitude'] if isinstance(x['magnitude'], (int, float)) else float('inf'))

        return visible

    def _calculate_planet_magnitude(self, t, planet_body, planet_name: str) -> float | None:
        try:
            astrometric = self.earth.at(t).observe(planet_body)
            magnitude = planetary_magnitude(astrometric)

            if isinstance(magnitude, np.ndarray):
                magnitude = float(magnitude.item())

            return round(magnitude, 2)
        except Exception as e:
            logger.error(f"Error calculating magnitude for {planet_name}: {e}")
            return None

    @staticmethod
    def _get_brightest_stars(observer, t, weather_data: Dict[str, Any] | None = None, limit: int = 8) -> List[Dict[str, Any]]:
        try:
            notable_stars = [
                {'name': 'Sirius', 'ra_hours': 6.7525, 'dec_degrees': -16.7161, 'magnitude': -1.46},
                {'name': 'Canopus', 'ra_hours': 6.3992, 'dec_degrees': -52.6956, 'magnitude': -0.74},
                {'name': 'Arcturus', 'ra_hours': 14.2610, 'dec_degrees': 19.1824, 'magnitude': -0.05},
                {'name': 'Vega', 'ra_hours': 18.6156, 'dec_degrees': 38.7837, 'magnitude': 0.03},
                {'name': 'Capella', 'ra_hours': 5.2781, 'dec_degrees': 45.9980, 'magnitude': 0.08},
                {'name': 'Rigel', 'ra_hours': 5.2423, 'dec_degrees': -8.2017, 'magnitude': 0.13},
                {'name': 'Procyon', 'ra_hours': 7.6553, 'dec_degrees': 5.2247, 'magnitude': 0.34},
                {'name': 'Achernar', 'ra_hours': 1.6285, 'dec_degrees': -57.2367, 'magnitude': 0.46},
                {'name': 'Betelgeuse', 'ra_hours': 5.9195, 'dec_degrees': 7.4070, 'magnitude': 0.50, 'variable': True, 'variation': '±0.8'},
                {'name': 'Hadar', 'ra_hours': 14.0638, 'dec_degrees': -60.3730, 'magnitude': 0.61},
                {'name': 'Altair', 'ra_hours': 19.8464, 'dec_degrees': 8.8683, 'magnitude': 0.77},
                {'name': 'Acrux', 'ra_hours': 12.4433, 'dec_degrees': -63.0990, 'magnitude': 0.77},
                {'name': 'Aldebaran', 'ra_hours': 4.5987, 'dec_degrees': 16.5093, 'magnitude': 0.85, 'variable': True, 'variation': '±0.1'},
                {'name': 'Spica', 'ra_hours': 13.4199, 'dec_degrees': -11.1613, 'magnitude': 0.98},
                {'name': 'Antares', 'ra_hours': 16.4901, 'dec_degrees': -26.4320, 'magnitude': 1.06, 'variable': True, 'variation': '±0.15'},
                {'name': 'Pollux', 'ra_hours': 7.7553, 'dec_degrees': 28.0262, 'magnitude': 1.14},
                {'name': 'Fomalhaut', 'ra_hours': 22.9608, 'dec_degrees': -29.6222, 'magnitude': 1.16},
                {'name': 'Deneb', 'ra_hours': 20.6906, 'dec_degrees': 45.2803, 'magnitude': 1.25},
                {'name': 'Mimosa', 'ra_hours': 12.7953, 'dec_degrees': -59.6889, 'magnitude': 1.25},
                {'name': 'Regulus', 'ra_hours': 10.1395, 'dec_degrees': 11.9672, 'magnitude': 1.36},
                {'name': 'Adhara', 'ra_hours': 6.9771, 'dec_degrees': -28.9721, 'magnitude': 1.50},
                {'name': 'Castor', 'ra_hours': 7.5766, 'dec_degrees': 31.8883, 'magnitude': 1.58},
                {'name': 'Gacrux', 'ra_hours': 12.5194, 'dec_degrees': -57.1131, 'magnitude': 1.59},
                {'name': 'Shaula', 'ra_hours': 17.5600, 'dec_degrees': -37.1038, 'magnitude': 1.63},
                {'name': 'Bellatrix', 'ra_hours': 5.4188, 'dec_degrees': 6.3497, 'magnitude': 1.64},
                {'name': 'Elnath', 'ra_hours': 5.4381, 'dec_degrees': 28.6075, 'magnitude': 1.65},
                {'name': 'Miaplacidus', 'ra_hours': 9.2200, 'dec_degrees': -69.7172, 'magnitude': 1.68},
                {'name': 'Alnilam', 'ra_hours': 5.6036, 'dec_degrees': -1.2019, 'magnitude': 1.69},
                {'name': 'Alnair', 'ra_hours': 22.1372, 'dec_degrees': -46.9606, 'magnitude': 1.74},
                {'name': 'Alnitak', 'ra_hours': 5.6794, 'dec_degrees': -1.9425, 'magnitude': 1.77},
                {'name': 'Alioth', 'ra_hours': 12.9004, 'dec_degrees': 55.9598, 'magnitude': 1.77},
                {'name': 'Mirfak', 'ra_hours': 3.4054, 'dec_degrees': 49.8612, 'magnitude': 1.79},
                {'name': 'Dubhe', 'ra_hours': 11.0621, 'dec_degrees': 61.7511, 'magnitude': 1.79},
                {'name': 'Kaus Australis', 'ra_hours': 18.4029, 'dec_degrees': -34.3846, 'magnitude': 1.85},
                {'name': 'Wezen', 'ra_hours': 7.1397, 'dec_degrees': -26.3932, 'magnitude': 1.86},
                {'name': 'Alkaid', 'ra_hours': 13.7923, 'dec_degrees': 49.3133, 'magnitude': 1.86},
                {'name': 'Avior', 'ra_hours': 8.3753, 'dec_degrees': -59.5097, 'magnitude': 1.86},
                {'name': 'Sargas', 'ra_hours': 17.6218, 'dec_degrees': -42.9977, 'magnitude': 1.87},
                {'name': 'Menkalinan', 'ra_hours': 5.9925, 'dec_degrees': 44.9475, 'magnitude': 1.90},
                {'name': 'Atria', 'ra_hours': 16.8110, 'dec_degrees': -69.0278, 'magnitude': 1.92},
                {'name': 'Alhena', 'ra_hours': 6.6287, 'dec_degrees': 16.3994, 'magnitude': 1.93},
                {'name': 'Peacock', 'ra_hours': 20.4274, 'dec_degrees': -56.7350, 'magnitude': 1.94},
                {'name': 'Polaris', 'ra_hours': 2.5301, 'dec_degrees': 89.2641, 'magnitude': 1.98},
                {'name': 'Alphard', 'ra_hours': 9.4597, 'dec_degrees': -8.6586, 'magnitude': 1.98},
                {'name': 'Hamal', 'ra_hours': 2.1196, 'dec_degrees': 23.4624, 'magnitude': 2.00},
                {'name': 'Diphda', 'ra_hours': 0.7265, 'dec_degrees': -17.9866, 'magnitude': 2.04},
                {'name': 'Nunki', 'ra_hours': 18.9210, 'dec_degrees': -26.2967, 'magnitude': 2.05},
                {'name': 'Alpheratz', 'ra_hours': 0.1398, 'dec_degrees': 29.0905, 'magnitude': 2.06},
                {'name': 'Saiph', 'ra_hours': 5.7959, 'dec_degrees': -9.6697, 'magnitude': 2.06},
                {'name': 'Rasalhague', 'ra_hours': 17.5822, 'dec_degrees': 12.5600, 'magnitude': 2.08},
                {'name': 'Kochab', 'ra_hours': 14.8451, 'dec_degrees': 74.1553, 'magnitude': 2.08},
                {'name': 'Algieba', 'ra_hours': 10.3328, 'dec_degrees': 19.8414, 'magnitude': 2.08},
                {'name': 'Algol', 'ra_hours': 3.1362, 'dec_degrees': 40.9557, 'magnitude': 2.12, 'variable': True, 'variation': '±1.4'},
                {'name': 'Denebola', 'ra_hours': 11.8177, 'dec_degrees': 14.5721, 'magnitude': 2.14},
                {'name': 'Sadr', 'ra_hours': 20.3703, 'dec_degrees': 40.2567, 'magnitude': 2.23},
                {'name': 'Mizar', 'ra_hours': 13.3988, 'dec_degrees': 54.9254, 'magnitude': 2.23},
                {'name': 'Eltanin', 'ra_hours': 17.9434, 'dec_degrees': 51.4889, 'magnitude': 2.23},
                {'name': 'Schedar', 'ra_hours': 0.6753, 'dec_degrees': 56.5373, 'magnitude': 2.24},
                {'name': 'Caph', 'ra_hours': 0.1527, 'dec_degrees': 59.1497, 'magnitude': 2.28},
                {'name': 'Ankaa', 'ra_hours': 0.4381, 'dec_degrees': -42.3061, 'magnitude': 2.38},
                {'name': 'Enif', 'ra_hours': 21.7364, 'dec_degrees': 9.8750, 'magnitude': 2.40},
                {'name': 'Scheat', 'ra_hours': 23.0628, 'dec_degrees': 28.0828, 'magnitude': 2.42, 'variable': True, 'variation': '±0.2'},
                {'name': 'Sabik', 'ra_hours': 17.1733, 'dec_degrees': -15.7249, 'magnitude': 2.43},
                {'name': 'Alderamin', 'ra_hours': 21.3096, 'dec_degrees': 62.5853, 'magnitude': 2.44},
                {'name': 'Aludra', 'ra_hours': 7.4013, 'dec_degrees': -29.3031, 'magnitude': 2.45},
                {'name': 'Markab', 'ra_hours': 23.0793, 'dec_degrees': 15.2053, 'magnitude': 2.49},
                {'name': 'Menkar', 'ra_hours': 3.0380, 'dec_degrees': 4.0897, 'magnitude': 2.54},
                {'name': 'Gienah', 'ra_hours': 12.2634, 'dec_degrees': -17.5418, 'magnitude': 2.59},
                {'name': 'Unukalhai', 'ra_hours': 15.7378, 'dec_degrees': 6.4258, 'magnitude': 2.63},
                {'name': 'Zubenelgenubi', 'ra_hours': 14.8479, 'dec_degrees': -16.0417, 'magnitude': 2.75},
                {'name': 'Vindemiatrix', 'ra_hours': 13.0366, 'dec_degrees': 10.9592, 'magnitude': 2.85},
                {'name': 'Aljanah', 'ra_hours': 20.7706, 'dec_degrees': 33.9703, 'magnitude': 2.86},
                {'name': 'Acamar', 'ra_hours': 2.9710, 'dec_degrees': -40.3047, 'magnitude': 2.88},
                {'name': 'Pherkad', 'ra_hours': 15.3453, 'dec_degrees': 71.8340, 'magnitude': 3.00},
            ]

            visible_stars = []

            # Extract weather conditions
            conditions = get_temp_pressure_conditions(weather_data)
            temp_c = conditions['temperature_C']
            pressure = conditions['pressure_mbar']

            for star_data in notable_stars:
                star = Star(ra_hours=star_data['ra_hours'], dec_degrees=star_data['dec_degrees'])
                apparent = observer.at(t).observe(star).apparent()
                alt_geometric, az, _ = apparent.altaz()

                alt_apparent_deg = calculate_extended_refraction(alt_geometric.degrees, temp_c, pressure)

                if alt_apparent_deg > 0.0:
                    is_variable = star_data.get('variable', False)
                    variation = star_data.get('variation', None)

                    visible_stars.append({
                        'name': star_data['name'],
                        'altitude': round(alt_apparent_deg, 1),
                        'azimuth': round(az.degrees, 1),
                        'magnitude': star_data['magnitude'],
                        'is_variable': is_variable,
                        'variation': variation,
                    })


            visible_stars.sort(key=lambda x: x['magnitude'])
            return visible_stars[:limit]

        except Exception as e:
            logger.error(f"Error getting brightest stars: {e}")
            return []

    @staticmethod
    def _get_sky_condition(sun_altitude: float) -> Dict[str, Any]:
        if sun_altitude > 0.0:
            return {
                'condition': 'Daytime',
                'description': 'Planets and stars not visible'
            }
        elif sun_altitude > -6.0:
            return {
                'condition': 'Civil Twilight',
                'description': 'Brightest planets may be visible'
            }
        elif sun_altitude > -12.0:
            return {
                'condition': 'Nautical Twilight',
                'description': 'Bright stars and planets visible'
            }
        elif sun_altitude > -18.0:
            return {
                'condition': 'Astronomical Twilight',
                'description': 'Most stars and planets visible'
            }
        else:
            return {
                'condition': 'Full Night',
                'description': 'Optimal stargazing conditions'
            }

    @staticmethod
    def format_night_sky_message(sky_data: Dict[str, Any]) -> str:
        location_info = sky_data['location']
        sky_condition = sky_data['sky_condition']
        cloud_cover = sky_data['cloud_cover']

        message = f"<b>{location_info['city']}. {sky_data['date_formatted']}</b>\n"

        if sky_data['current_time']:
            message += f"\n<b>Current Time:</b> {sky_data['current_time']}\n\n"
        else:
            message += f"\n<b>Data for:</b> {sky_data['time']}\n\n"

        message += f"<b>Sky Condition:</b> {sky_condition['condition']}\n"
        message += f"<i>{sky_condition['description']}</i>\n\n"

        # Sun and Moon
        sun = sky_data['sun']
        moon = sky_data['moon']

        message += f"<b>Sun:</b> {'Above horizon' if sun['is_visible'] else 'Below horizon'}\n"
        message += f"<b>Moon:</b> {'Above horizon' if moon['is_visible'] else 'Below horizon'}\n\n"

        if cloud_cover is not None:
            message += f"<b>☁️ Cloud Cover:</b> {cloud_cover}%\n\n"

        planets = sky_data['planets']
        if planets:
            message += f"<b>🪐 Visible Planets ({len(planets)}):</b>\n"
            for planet in planets:
                message += f"\n<b>{planet['name']}</b>:\n"
                message += f"• Azimuth: {planet['azimuth']}°\n"
                message += f"• Altitude: {planet['altitude']}°\n"
                message += f"• Apparent Magnitude: {planet['magnitude']}\n"
            message += "\n"
        else:
            message += "<b>🪐 Planets:</b> None currently visible\n\n"

        stars = sky_data['stars']
        if stars:
            message += f"<b>✨ Visible Brightest Stars:</b>\n"
            for star in stars:
                message += f"\n<b>{star['name']}</b>:\n"
                message += f"• Azimuth: {star['azimuth']}°\n"
                message += f"• Altitude: {star['altitude']}°\n"
                mag_text = f"{star['magnitude']}"
                if star.get('is_variable', False):
                    variation = star.get('variation') or '±0.3'
                    mag_text += f" ({variation})"
                message += f"• Apparent Magnitude: {mag_text}\n"
            message += "\n"
        else:
            message += "<b>✨ Stars:</b> Not visible from current location\n\n"

        # Viewing tips
        if sky_data['is_night']:
            message += "<i>💡 Find a dark location away from city lights for best viewing</i>"
        else:
            message += "<i>💡 Wait for nighttime for optimal stargazing conditions</i>"

        return message


night_sky_service = NightSkyService()

def get_user_today(user: User) -> date:
    try:
        tz = pytz.timezone(user.timezone)
        now = datetime.now(tz)
        return now.date()
    except (pytz.exceptions.UnknownTimeZoneError, ValueError, AttributeError):
        return date.today()