import aiohttp, logging, pytz, re
from datetime import datetime, date
from typing import Dict, Any, List
from config.settings import NASA_API_KEY
from .customerror import NoAPIError
from database.models import User

logger = logging.getLogger(__name__)


class NASAAstronomyService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or NASA_API_KEY
        if not self.api_key:
            raise NoAPIError(
                "NASA API key is required. Set NASA_API_KEY environment variable or pass api_key parameter.")

        self.endpoints = {
            'apod': "https://science.nasa.gov/wp-json/wp/v2/apod-basic",  # Astronomy Picture of the Day
            'neo': "https://api.nasa.gov/neo/rest/v1/feed",  # Near Earth Objects
        }

    async def get_space_data(self, user: User = None) -> List[Dict[str, Any]] | None:
        target_date = self._get_user_date(user) if user and user.has_location else date.today()
        space_data = []

        # 1. Astronomy Picture of the Day
        apod_data = await self._get_apod(target_date)
        if apod_data:
            space_data.append({
                'type': 'apod',
                'title': 'NASA Astronomy Picture of the Day',
                'data': apod_data
            })

        # 2. Near Earth Objects
        neo_data = await self._get_near_earth_objects(target_date)
        if neo_data:
            space_data.append({
                'type': 'neo',
                'title': 'Near Earth Objects Today',
                'data': neo_data
            })

        return space_data if space_data else None

    async def _get_apod(self, target_date: date) -> Dict[str, Any] | None:
        params = {
            'api_key': self.api_key,
            'date': target_date.isoformat()
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.endpoints['apod'], params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        item = data[0] if isinstance(data, list) and data else data

                        if isinstance(item, dict) and item.get('title'):
                            # Normalize copyright/credit string
                            copyright_text = item.get('copyright') or item.get('credit', 'NASA')
                            if copyright_text:
                                copyright_text = copyright_text.replace('\n', ' ').strip()

                            # Clean up raw explanation HTML (strip tags except <a> links)
                            raw_explanation = item.get('explanation', '')
                            clean_text = re.sub(r'^\s*(?:<(?:strong|b)>)?Explanation:?(?:</(?:strong|b)>)?\s*', '', raw_explanation, flags=re.IGNORECASE)
                            clean_text = re.sub(r'<br\s*/?>', '\n', clean_text, flags=re.IGNORECASE)

                            def keep_links_only(match):
                                tag = match.group(0)
                                if re.match(r'^<\s*a\b', tag, re.IGNORECASE) or re.match(r'^<\s*/\s*a\s*>', tag, re.IGNORECASE):
                                    return tag
                                return ''

                            clean_explanation = re.sub(r'<[^>]+>', keep_links_only, clean_text).strip()

                            image_url = item.get('hdurl') or item.get('url') or ''
                            if image_url:
                                image_url = image_url.split('?')[0]
                            post_url = item.get('permalink') or item.get('url') or ''

                            return {
                                'title': item.get('title', 'Unknown'),
                                'explanation': clean_explanation,
                                'url': image_url,
                                'permalink': post_url,
                                'media_type': item.get('media_type', 'image'),
                                'date': item.get('date', target_date.isoformat()),
                                'copyright': copyright_text
                            }
        except Exception as e:
            logger.error(f"Error fetching APOD: {e}")

        return None

    async def _get_near_earth_objects(self, target_date: date) -> Dict[str, Any] | None:
        params = {
            'api_key': self.api_key,
            'start_date': target_date.isoformat(),
            'end_date': target_date.isoformat()
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.endpoints['neo'], params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        date_key = target_date.isoformat()
                        neo_objects = data.get('near_earth_objects', {}).get(date_key, [])

                        if not neo_objects:
                            return None

                        sorted_objects = sorted(
                            neo_objects,
                            key=lambda x: float(x['close_approach_data'][0]['miss_distance']['kilometers'])
                        )

                        result = {
                            'count': len(sorted_objects),
                            'objects': []
                        }

                        for neo in sorted_objects[:3]:
                            approach_data = neo['close_approach_data'][0]
                            result['objects'].append({
                                'name': neo.get('name', ''),
                                'diameter_min': neo.get('estimated_diameter', {}).get('meters', {}).get(
                                    'estimated_diameter_min', 0),
                                'diameter_max': neo.get('estimated_diameter', {}).get('meters', {}).get(
                                    'estimated_diameter_max', 0),
                                'miss_distance_km': float(approach_data.get('miss_distance', {}).get('kilometers', 0)),
                                'velocity_kmh': float(
                                    approach_data.get('relative_velocity', {}).get('kilometers_per_hour', 0)),
                                'is_potentially_hazardous': neo.get('is_potentially_hazardous_asteroid', False)
                            })

                        return result

        except Exception as e:
            logger.error(f"Error fetching NEO data: {e}")

        return None

    @staticmethod
    def _get_user_date(user: User) -> date:
        try:
            if user.timezone:
                tz = pytz.timezone(user.timezone)
                now = datetime.now(tz)
                return now.date()
        except Exception as e:
            logger.error(f"Error getting user date: {e}")

        return date.today()

    @staticmethod
    def _truncate_with_link(text: str, max_length: int = 420, full_url: str = None) -> str:
        if len(text) <= max_length:
            return text

        # Find a good breaking point (sentence end, period, or space)
        truncate_point = max_length
        for i in range(max_length - 50, max_length):
            if i < len(text) and text[i] in '.!?':
                truncate_point = i + 1
                break
        else:
            # Find last space before max_length
            for i in range(max_length - 1, max_length - 100, -1):
                if i < len(text) and text[i] == ' ':
                    truncate_point = i
                    break

        truncated = text[:truncate_point]

        # Prevent breaking inside an unclosed HTML tag (< ... >)
        last_lt = truncated.rfind('<')
        last_gt = truncated.rfind('>')
        if last_lt > last_gt:
            truncated = truncated[:last_lt]

        # Check and fix <a> tag balance to prevent Telegram parsing errors
        open_tags = list(re.finditer(r'<\s*a\b[^>]*>', truncated, flags=re.IGNORECASE))
        close_tags = list(re.finditer(r'<\s*/\s*a\s*>', truncated, flags=re.IGNORECASE))

        if len(open_tags) > len(close_tags):
            last_open = open_tags[-1]
            truncated = truncated[:last_open.start()]

        truncated = truncated.strip()
        result = truncated + "..."

        if full_url:
            result += f" <a href='{full_url}'>Read more</a>"

        return result

    def format_space_message(self, space_data: List[Dict[str, Any]], user: User = None) -> str:
        if not space_data:
            return "❌ <b>Data unavailable</b>\n\nPlease try again later."
        try:
            user_date = self._get_user_date(user) if user and user.has_location else date.today()
            header = f"<b>🪐 Space Today • {user_date.strftime('%B %d, %Y')}</b>\n\n"
        except Exception as e:
            logger.warning(f"Error formatting date header: {e}")
            header = f"<b>🪐 Space Today • {date.today().strftime('%B %d, %Y')}</b>\n\n"

        message = header

        for item in space_data:
            item_type = item['type']
            title = item['title']
            data = item['data']

            message += f"<b>{title}</b>\n"

            if item_type == 'apod':
                message += f"<b>Title:</b> {data['title']}\n"

                media_type = data.get('media_type', 'image')
                if data.get('url'):
                    link_text = "🎬 Watch Video" if media_type == 'video' else "🖼 Full Image"
                    message += f"<b>View:</b> <a href='{data['url']}'>{link_text}</a>\n"

                if data.get('copyright'):
                    message += f"<b>Credit:</b> {data['copyright']}\n"

                explanation = data.get('explanation', '')

                # Create link to NASA APOD page for full text
                apod_web_url = data.get('permalink')

                # Truncate with link to full NASA page
                if explanation:
                    truncated_explanation = self._truncate_with_link(explanation, 420, apod_web_url)
                    message += f"<b>Description:</b> {truncated_explanation}\n"

            elif item_type == 'neo':
                message += f"<b>Total objects detected:</b> {data['count']}\n"
                if data['objects']:
                    message += "<b>Closest approaches:</b>\n"

                    for i, obj in enumerate(data['objects'], 1):
                        name = obj['name'].replace('(', '').replace(')', '').replace('  ', ' ')
                        if len(name) > 20:
                            name = name[:20] + ".."

                        hazard = "⚠️ " if obj['is_potentially_hazardous'] else ""

                        dist = f"{obj['miss_distance_km']:,.0f} km".replace(',', ' ')

                        size_min = int(obj['diameter_min'])
                        size_max = int(obj['diameter_max'])
                        size = f"{size_min}-{size_max}m"

                        speed = f"{obj['velocity_kmh']:,.0f} km/h".replace(',', ' ')

                        message += f"{i}. {hazard}{name}\n"
                        message += f"    Distance: {dist}\n"
                        message += f"    Size: {size}\n"
                        message += f"    Speed: {speed}\n"
                        if i < len(data['objects']):
                            message += f"\n"

            message += "\n"

        message += "<b>Source:</b> NASA Open Data Portal\n"
        message += "<b>Updates:</b> Daily"

        return message


space_service = NASAAstronomyService()