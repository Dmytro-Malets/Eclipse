import aiohttp, logging, random
from typing import Dict, Any, List
from config.settings import NASA_API_KEY
from .customerror import NoAPIError

logger = logging.getLogger(__name__)


class MarsRoverService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or NASA_API_KEY
        if not self.api_key:
            raise NoAPIError(
                "NASA API key is required. Set NASA_API_KEY environment variable or pass api_key parameter.")

        self.base_url = "https://api.nasa.gov/mars-photos/api/v1/rovers"

        self.rover_info = {
            'perseverance': {
                'name': 'Perseverance'
            },
            'curiosity': {
                'name': 'Curiosity'
            }
        }

        self.preferred_cameras = {
            'perseverance': [
                'FRONT_HAZCAM_LEFT_A', 'FRONT_HAZCAM_RIGHT_A', # Front Hazard Avoidance Camera
                'NAVCAM_LEFT', 'NAVCAM_RIGHT', # Navigation Camera
                'REAR_HAZCAM_LEFT', 'REAR_HAZCAM_RIGHT', # Rear Hazard Avoidance Camera
                'MCZ_LEFT', 'MCZ_RIGHT', # Mast Camera Zoom
                'SHERLOC_WATSON', 'SUPERCAM_RMI' # SHERLOC WATSON Camera, SuperCam Remote Micro Imager
            ],
            'curiosity': [
                'FHAZ_LEFT_B', 'FHAZ_RIGHT_B', # Front Hazard Avoidance Camera
                'MARDI', # Mars Descent Imager
                'NAV_LEFT_B', 'NAV_RIGHT_B', # Navigation Camera
                'RHAZ_LEFT_B', 'RHAZ_RIGHT_B', # Rear Hazard Avoidance Camera
                'MAST_LEFT', 'MAST_RIGHT', # Mast Camera

            ]
        }

        self.curiosity_camera_full_names_map = {
            'FHAZ': 'Front Hazard Avoidance Camera',
            'RHAZ': 'Rear Hazard Avoidance Camera',
            'MAST': 'Mast Camera',
            'CHEMCAM': 'Chemistry and Camera Complex',
            'MAHLI': 'Mars Hand Lens Imager',
            'MARDI': 'Mars Descent Imager',
            'NAV': 'Navigation Camera'
        }

    async def get_rover_latest_photos(self, rover_name: str, max_photos: int = 10) -> Dict[str, Any] | None:
        rover_key = rover_name.lower()

        if rover_key not in self.preferred_cameras:
            logger.error(f"Unknown rover: {rover_name}")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                manifest_url = f"https://api.nasa.gov/mars-photos/api/v1/manifests/{rover_key}?api_key={self.api_key}"
                async with session.get(manifest_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get rover manifest: {response.status}")
                        return None
                    manifest = await response.json()
                    rover_data = manifest.get('photo_manifest', {})
                    max_sol = rover_data.get('max_sol')
                    status = rover_data.get('status', 'unknown')
                    if not max_sol:
                        logger.error(f"No max_sol found for {rover_name}")
                        return None

                available_photos = []
                # Search on the last sol
                photos_url = f"{self.base_url}/{rover_key}/photos?sol={max_sol}&api_key={self.api_key}"
                async with session.get(photos_url) as photos_response:
                    if photos_response.status == 200:
                        photos_data = await photos_response.json()
                        available_photos = photos_data.get('photos', [])

                # # If there are no photos on the latest sol, try the previous one to avoid an empty response
                if not available_photos and max_sol:
                    test_sol = max_sol - 1
                    logger.warning(f"No photos on sol {max_sol}. Trying sol {test_sol} for {rover_name}")
                    test_url = f"{self.base_url}/{rover_key}/photos?sol={test_sol}&api_key={self.api_key}"
                    async with session.get(test_url) as test_response:
                        if test_response.status == 200:
                            test_data = await test_response.json()
                            available_photos = test_data.get('photos', [])
                            if available_photos:
                                max_sol = test_sol

                if not available_photos:
                    logger.warning(f"No photos found for {rover_name} in recent sols.")
                    return None

                final_photos = []
                used_photo_ids = set()

                # Step 1: One photo from each priority camera
                preferred_cameras = self.preferred_cameras.get(rover_key, [])
                for camera_name in preferred_cameras:
                    if len(final_photos) >= max_photos:
                        break

                    camera_photos = [p for p in available_photos if p.get('camera', {}).get('name') == camera_name]
                    if camera_photos:
                        prepare_photo = random.choice(camera_photos)
                        if prepare_photo['id'] not in used_photo_ids:
                            final_photos.append(prepare_photo)
                            used_photo_ids.add(prepare_photo['id'])

                # Step 2: Randomly add photos from all available cameras
                if len(final_photos) < max_photos:
                    remaining_photos = [p for p in available_photos if p['id'] not in used_photo_ids]

                    if remaining_photos:
                        random.shuffle(remaining_photos)
                        needed = max_photos - len(final_photos)
                        final_photos.extend(remaining_photos[:needed])

                formatted_photos = []
                for photo in final_photos:
                    img_src = photo.get('img_src', '').replace('http://', 'https://')
                    formatted_photos.append({
                        'id': photo.get('id'), 'img_src': img_src,
                        'earth_date': photo.get('earth_date'), 'sol': photo.get('sol'),
                        'camera_name': photo.get('camera', {}).get('name', 'Unknown'),
                        'camera_full_name': photo.get('camera', {}).get('full_name', 'Unknown Camera')
                    })

                return {
                    'rover_info': self.rover_info.get(rover_key, {}), 'sol': max_sol,
                    'status': status, 'total_photos_available': len(available_photos),
                    'photos_returned': len(formatted_photos), 'photos': formatted_photos
                }

        except Exception as e:
            logger.error(f"Error fetching photos for {rover_name}: {e}")
            return None

    async def get_available_rovers(self) -> List[Dict[str, Any]]:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}?api_key={self.api_key}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        rovers_data = data.get('rovers', [])

                        active_rovers = []
                        for rover in rovers_data:
                            rover_name = rover.get('name', '').lower()
                            if rover_name in self.rover_info and rover.get('status') == 'active':
                                rover_info = self.rover_info[rover_name].copy()
                                rover_info.update({
                                    'max_sol': rover.get('max_sol'),
                                    'max_date': rover.get('max_date'),
                                    'total_photos': rover.get('total_photos')
                                })
                                active_rovers.append(rover_info)

                        return active_rovers

        except Exception as e:
            logger.error(f"Error fetching available rovers: {e}")

        # Fallback - return a static list
        return [
            {**self.rover_info['perseverance'], 'max_sol': 'Unknown', 'total_photos': 'Unknown'},
            {**self.rover_info['curiosity'], 'max_sol': 'Unknown', 'total_photos': 'Unknown'}
        ]

    @staticmethod
    def format_rover_selection_message() -> str:
        return (
            "<b>Mars Rover Photo Gallery</b>\n\n"
            "Select a Mars rover to view latest surface photos:\n\n"
            "<b>Curiosity</b> - Active since August 2012\n\n"
            "<b>Perseverance</b> - Active since February 2021\n\n"
            "<i>Each rover has unique cameras and viewing angles</i>"
        )

    def format_rover_photos_message(self, rover_data: Dict[str, Any]) -> str:
        rover_info = rover_data['rover_info']
        rover_name_lower = rover_info.get('name', '').lower()

        message = f"<b>{rover_info['name']} Mars Rover</b>\n\n"
        message += f"<b>Sol:</b> {rover_data['sol']} (Martian day)\n"
        message += f"<b>Photos sent:</b> {rover_data['photos_returned']}\n"
        message += f"<b>Total available:</b> {rover_data['total_photos_available']}\n\n"

        if rover_data['photos']:
            message += "<b>Camera types in this collection:</b>\n"

            camera_photos = {}
            for i, photo in enumerate(rover_data['photos'], 1):

                if rover_name_lower == 'curiosity':
                    curiosity_short_name = photo['camera_name']
                    base_name = curiosity_short_name.split('_')[0]

                    human_readable_base = self.curiosity_camera_full_names_map.get(base_name)

                    if human_readable_base:
                        if 'LEFT' in curiosity_short_name:
                            final_camera_name = f"{human_readable_base} - Left"
                        elif 'RIGHT' in curiosity_short_name:
                            final_camera_name = f"{human_readable_base} - Right"
                        else:
                            final_camera_name = human_readable_base
                    else:
                        final_camera_name = curiosity_short_name
                else:
                    final_camera_name = photo.get('camera_full_name', photo['camera_name'])

                if final_camera_name not in camera_photos:
                    camera_photos[final_camera_name] = []
                camera_photos[final_camera_name].append(str(i))

            for camera_name in sorted(camera_photos.keys()):
                photo_numbers = camera_photos[camera_name]
                if len(photo_numbers) == 1:
                    message += f"• {camera_name} (#{photo_numbers[0]})\n"
                else:
                    numbers_str = ", ".join(photo_numbers)
                    message += f"• {camera_name} (#{numbers_str})\n"

            message += "\n"

        message += "<b>Source:</b> NASA Mars Exploration Program"
        return message


mars_rover_service = MarsRoverService()