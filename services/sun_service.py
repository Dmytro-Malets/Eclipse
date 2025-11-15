import logging, pytz
from datetime import datetime, date, time, timedelta
from typing import Dict, Any
from skyfield.api import load, wgs84, utc
from skyfield import almanac
from database.models import User
from .uv_service import UVService

logger = logging.getLogger(__name__)


class SunService:
    def __init__(self):
        self.uv_service = UVService()
        # Load ephemeris data
        self.ts = load.timescale()
        self.eph = load('de421.bsp') # NASA JPL ephemeris
        self.earth = self.eph['earth']
        self.sun = self.eph['sun']

    async def get_sun_times(self, user: User, target_date: date = None) -> Dict[str, Any] | None:
        if not user.has_location:
            return None

        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)
            user_today = now.date()

            if target_date is None:
                target_date = user_today

            # Create observer location
            topos = wgs84.latlon(user.latitude, user.longitude)
            observer = self.earth + wgs84.latlon(user.latitude, user.longitude)

            # Determine the start and end of the 24-hour search range, localized to the user's timezone
            start_time_of_day = datetime.combine(target_date, time(0, 0))
            start_datetime_local = tz.localize(start_time_of_day)
            end_datetime_local = start_datetime_local + timedelta(days=1)

            t0 = self.ts.from_datetime(start_datetime_local.astimezone(utc))
            t1 = self.ts.from_datetime(end_datetime_local.astimezone(utc))

            # Get sunrise and sunset
            rise_set_data = self._calculate_sun_rise_set(topos, t0, t1, tz)
            sunrise = rise_set_data['sunrise']
            sunset = rise_set_data['sunset']

            # Get a solar noon
            solar_noon_dt = self._calculate_solar_noon(topos, t0, t1, tz)

            # Calculate sun position at solar noon and determine display time
            if noon_pos := (self._get_sun_position(observer, solar_noon_dt) if solar_noon_dt else None):
                solar_noon_dt_display = None if not noon_pos['is_up'] else solar_noon_dt
            else:
                solar_noon_dt_display = None

            # Get current position (for today only)
            sun_position = self._get_sun_position(observer, now) if target_date == user_today else None

            # Get the UV index (for today only)
            uv_data = None
            if target_date == user_today and self.uv_service:
                try:
                    uv_data = await self.uv_service.get_uv_index(user)
                except Exception as e:
                    logger.warning(f"UV Index could not be loaded: {e}")

            # Calculation of day length and status
            day_length_formatted = None
            sun_status = None

            if sunrise and sunset:
                if sunrise < sunset:
                    day_length = sunset - sunrise
                    day_length_formatted = self._format_duration(day_length)
                    if target_date == user_today:
                        sun_status = self._determine_sun_status(now, {'sunrise': sunrise, 'sunset': sunset})
                else:
                    day_part1 = sunset - start_datetime_local
                    day_part2 = end_datetime_local - sunrise
                    total_daylight = day_part1 + day_part2
                    day_length_formatted = self._format_duration(total_daylight)

                    if target_date == user_today:
                        if now < sunset:
                            sun_status = f"<b>Sun sets in:</b> {self._format_time_until(sunset - now)}"
                        elif now < sunrise:
                            sun_status = f"<b>Sun rises in:</b> {self._format_time_until(sunrise - now)}"
                        else:
                            sun_status = "<b>Sun is up</b>"

            elif not sunrise and not sunset:
                if noon_pos:
                    if noon_pos['is_up']:
                        day_length_formatted = "24h"
                        if target_date == user_today:
                            sun_status = "<b>Sun is up (Polar Day)</b>"
                    else:
                        day_length_formatted = "0s"
                        if target_date == user_today:
                            sun_status = "<b>Sun is down (Polar Night)</b>"

            elif not sunrise and sunset:
                day_length = sunset - start_datetime_local
                day_length_formatted = self._format_duration(day_length)

                if target_date == user_today:
                    if now < sunset:
                        sun_status = f"<b>Sun sets in:</b> {self._format_time_until(sunset - now)}"
                    else:
                        sun_status = "<b>Sun has set</b>"

            elif sunrise and not sunset:
                day_length = end_datetime_local - sunrise
                day_length_formatted = self._format_duration(day_length)

                if target_date == user_today:
                    if now < sunrise:
                        sun_status = f"<b>Sun rises in:</b> {self._format_time_until(sunrise - now)}"
                    else:
                        sun_status = "<b>Sun is up</b>"

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'date': target_date.strftime('%Y-%m-%d'),
                'date_formatted': target_date.strftime('%A, %B %d, %Y'),
                'sunrise': sunrise.strftime('%H:%M:%S') if sunrise else None,
                'sunset': sunset.strftime('%H:%M:%S') if sunset else None,
                'solar_noon': solar_noon_dt_display.strftime('%H:%M:%S') if solar_noon_dt_display else None,
                'day_length': day_length_formatted,
                'sun_status': sun_status,
                'current_time': now.strftime('%H:%M:%S') if target_date == user_today else None
            }

            if sun_position:
                result['current_position'] = sun_position

            if uv_data is not None:
                result['uv_data'] = uv_data

            return result

        except Exception as e:
            logger.error(f"Error calculating sun times for user {user.user_id}: {e}", exc_info=True)
            return None

    def _calculate_sun_rise_set(self, topos, t0, t1, tz: pytz.tzinfo.BaseTzInfo) -> Dict[str, datetime | None]:
        try:
            f = almanac.risings_and_settings(self.eph, self.sun, topos, radius_degrees = 16.0/60.0)

            f.step_days = 0.001

            times, events = almanac.find_discrete(t0, t1, f)

            sunrise_time = None
            sunset_time = None

            for time_obj, event in zip(times, events):
                time_local = time_obj.utc_datetime().replace(tzinfo=utc).astimezone(tz)
                if event == 1 and sunrise_time is None:  # 1 = Rise
                    sunrise_time = time_local
                elif event == 0 and sunset_time is None:  # 0 = Set
                    sunset_time = time_local

            return {'sunrise': sunrise_time, 'sunset': sunset_time}

        except Exception as e:
            logger.error(f"Error calculating sun rise/set: {e}")
            return {'sunrise': None, 'sunset': None}

    def _calculate_solar_noon(self, topos, t0, t1, tz: pytz.tzinfo.BaseTzInfo) -> datetime | None:
        try:
            f = almanac.meridian_transits(self.eph, self.sun, topos)
            times, events = almanac.find_discrete(t0, t1, f)

            for time_obj, event in zip(times, events):
                if event == 1:  # 1 = Meridian transit
                    time_local = time_obj.utc_datetime().replace(tzinfo=utc).astimezone(tz)
                    return time_local

            return None

        except Exception as e:
            logger.error(f"Error calculating solar noon: {e}")
            return None

    def _get_sun_position(self, observer, target_datetime: datetime) -> Dict[str, Any] | None:
        try:
            t = self.ts.from_datetime(target_datetime.astimezone(utc))
            sun_obs = observer.at(t).observe(self.sun).apparent()

            alt, az, _ = sun_obs.altaz()

            return {
                'altitude': round(alt.degrees, 1),
                'azimuth': round(az.degrees, 1),
                'is_up': alt.degrees > (-34.0/60.0 - 16.0/60.0)
            }
        except Exception as e:
            logger.error(f"Error getting sun position: {e}")
            return None

    @staticmethod
    def _format_duration(duration: timedelta) -> str:
        total_seconds = int(duration.total_seconds())
        if total_seconds < 0:
            total_seconds = 0

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if (hours == 0 and minutes == 0) or seconds > 0:
            parts.append(f"{seconds}s")

        if not parts:
            return "0s"
        return " ".join(parts)

    @staticmethod
    def _format_time_until(time_delta: timedelta) -> str:
        total_seconds = int(time_delta.total_seconds())
        if total_seconds < 0:
            total_seconds = 0

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _determine_sun_status(now: datetime, sun_times: Dict[str, datetime]) -> str:
        if now < sun_times['sunrise']:
            time_to_sunrise = sun_times['sunrise'] - now
            formatted_time = SunService._format_time_until(time_to_sunrise)
            return f"<b>Sun rises in:</b> {formatted_time}"
        elif now < sun_times['sunset']:
            time_to_sunset = sun_times['sunset'] - now
            formatted_time = SunService._format_time_until(time_to_sunset)
            return f"<b>Sun sets in:</b> {formatted_time}"
        else:
            return "<b>Sun has set</b>"

    @staticmethod
    def format_sun_info_message(sun_data: Dict[str, Any]) -> str:
        location_info = sun_data['location']

        def safe(val):
            return val if val is not None else "—"

        message = f"<b>{location_info['city']}. {sun_data['date_formatted']}</b>\n"
        if sun_data['current_time']:
            message += f"\n<b>Current Time:</b> {sun_data['current_time']}\n\n"
        else:
            message += f"\n"

        message += f"🌅 <b>Sunrise:</b> {safe(sun_data.get('sunrise'))}\n"
        message += f"🌇 <b>Sunset:</b> {safe(sun_data.get('sunset'))}\n"
        message += f"☀️ <b>Solar Noon:</b> {safe(sun_data.get('solar_noon'))}\n"
        message += f"⏱ <b>Day Length:</b> {safe(sun_data.get('day_length'))}"

        if sun_data.get('current_time'):
            sun_status = sun_data.get('sun_status')
            if sun_status:
                message += f"\n\n{sun_status}\n\n"
            else:
                message += f"\n\n"

            if 'uv_data' in sun_data and sun_data['uv_data'] is not None:
                uv = sun_data['uv_data']
                message += f"<b>UV Index:</b> {uv['uv_index']} {uv['color']}\n\n"

            if 'current_position' in sun_data:
                pos = sun_data['current_position']
                message += f"<b>Current Sun Position:</b>\n"
                message += f"• <b>Azimuth:</b> {safe(pos.get('azimuth'))}°\n"
                message += f"• <b>Altitude:</b> {safe(pos.get('altitude'))}°\n"
                message += f"• <b>Status:</b> {'Above horizon' if pos.get('is_up') else 'Below horizon'}"

        return message


sun_service = SunService()

def get_user_today(user: User) -> date:
    try:
        tz = pytz.timezone(user.timezone)
        now = datetime.now(tz)
        return now.date()
    except (pytz.exceptions.UnknownTimeZoneError, ValueError, AttributeError):
        return date.today()