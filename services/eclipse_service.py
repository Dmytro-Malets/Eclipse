import logging, pytz
from datetime import datetime, timedelta
from typing import Dict, Any, List
from skyfield.api import load, wgs84
from skyfield import eclipselib
from database.models import User

logger = logging.getLogger(__name__)


class EclipseService:
    def __init__(self):
        self.ts = load.timescale()
        self.eph = load('de421.bsp')
        self.earth = self.eph['earth']
        self.moon = self.eph['moon']

    async def get_upcoming_lunar_eclipses(self, user: User, max_eclipses: int = 5) -> Dict[str, Any] | None:
        if not user.has_location:
            return None

        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)

            # Search for next 10 years to ensure we find enough eclipses
            t_start = self.ts.from_datetime(now.astimezone(pytz.utc))
            t_end = self.ts.from_datetime((now + timedelta(days=3650)).astimezone(pytz.utc))

            # Find lunar eclipses
            lunar_eclipses = self._find_lunar_eclipses(t_start, t_end, user)

            # Take only requested number
            upcoming = lunar_eclipses[:max_eclipses] if len(lunar_eclipses) >= max_eclipses else lunar_eclipses

            if not upcoming:
                return None

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'eclipses': upcoming
            }

            return result

        except Exception as e:
            logger.error(f"Error calculating lunar eclipses for user {user.user_id}: {e}")
            return None

    def _find_lunar_eclipses(self, t_start, t_end, user: User) -> List[Dict[str, Any]]:
        eclipses = []
        try:
            t, y, details = eclipselib.lunar_eclipses(t_start, t_end, self.eph)

            tz = pytz.timezone(user.timezone)
            observer = self.earth + wgs84.latlon(user.latitude, user.longitude)

            for i in range(len(t)):
                umbral_magnitude = details['umbral_magnitude'][i]
                penumbral_magnitude = details['penumbral_magnitude'][i]
                eclipse_type = self._determine_lunar_eclipse_type(umbral_magnitude)

                peak_time = t[i]
                peak_time_local = peak_time.astimezone(tz)
                moon_obs = observer.at(peak_time).observe(self.moon).apparent()
                alt, az, _ = moon_obs.altaz()
                is_visible = alt.degrees > 0

                eclipses.append({
                    'eclipse_type': eclipse_type,
                    'peak_time': peak_time_local,
                    'date_formatted': peak_time_local.strftime('%B %d, %Y'),
                    'time_formatted': peak_time_local.strftime('%H:%M:%S'),
                    'is_visible': is_visible,
                    'umbral_magnitude': round(umbral_magnitude, 3),
                    'penumbral_magnitude': round(penumbral_magnitude, 3),
                    'altitude': round(alt.degrees, 1) if is_visible else None,
                    'azimuth': round(az.degrees, 1) if is_visible else None
                })

        except Exception as e:
            logger.error(f"Error finding lunar eclipses: {e}")

        return eclipses

    @staticmethod
    def _determine_lunar_eclipse_type(umbral_magnitude: float) -> str:
        if umbral_magnitude <= 0:
            return "Penumbral"
        elif 0 < umbral_magnitude < 1:
            return "Partial"
        else:
            return "Total"

    @staticmethod
    def format_eclipse_message(eclipse_data: Dict[str, Any]) -> str:
        if not eclipse_data or not eclipse_data.get('eclipses'):
            return "<b>No upcoming lunar eclipses found</b>"

        location_info = eclipse_data['location']
        eclipses = eclipse_data['eclipses']

        tz = pytz.timezone(location_info['timezone'])
        now = datetime.now(tz)
        current_time = now.strftime('%H:%M:%S')
        date_formatted = now.strftime('%A, %B %d, %Y')

        message = f"<b>{location_info['city']}. {date_formatted}</b>\n\n"
        message += f"<b>Current Time:</b> {current_time}\n\n"

        for idx, eclipse in enumerate(eclipses, 1):
            message += f"<b>{idx}. {eclipse['eclipse_type']} Lunar Eclipse</b>\n"
            message += f"<b>Date:</b> {eclipse['date_formatted']}\n"
            message += f"<b>Peak Time:</b> {eclipse['time_formatted']}\n"
            message += f"<b>Penumbral Magnitude:</b> {eclipse['penumbral_magnitude']}\n"
            if eclipse['umbral_magnitude'] > 0:
                message += f"<b>Umbral Magnitude:</b> {eclipse['umbral_magnitude']}\n"

            if eclipse['is_visible']:
                message += f"<b>Visibility:</b> Visible from your location\n"
                message += f"<b>Azimuth (at peak):</b> {eclipse['azimuth']}°\n"
                message += f"<b>Altitude (at peak):</b> {eclipse['altitude']}°\n"
            else:
                message += f"<b>Visibility:</b> Not visible (Moon below horizon)\n"

            if idx < len(eclipses):
                message += "\n"

        return message


eclipse_service = EclipseService()