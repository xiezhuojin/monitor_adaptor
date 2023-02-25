from typing import List, Dict, Callable, Tuple
from threading import Thread
from queue import Queue, Empty
from time import time
from math import atan2, degrees, sqrt, pow
import asyncio
import json

from websockets import serve
from geographiclib.geodesic import Geodesic


class Track:

    def __init__(self, id: str, lng: float, lat: float, alt: float, track_at: float,
                 type: str, size: str) -> None:
        self.id = id
        self.lng = lng
        self.lat = lat
        self.alt = alt
        self.track_at = track_at

        self.type = type
        self.size = size


class Device:

    def __init__(self, id: str, type: str, lng: float, lat: float, name: str,
                 functional: bool) -> None:
        self.id = id
        self.type = type
        self.lng = lng
        self.lat = lat

        self.name = name
        self.functional = functional


class Airplane:

    def __init__(self, id: str, lng: float, lat: float, alt: float,
                 track_at: float, name: str) -> None:
        self.id = id
        self.lng = lng
        self.lat = lat
        self.alt = alt
        self.track_at = track_at
        self.name = name


class CylinderZone:

    def __init__(self, id: str, type: str, lng: float, lat: float,
                 radius_in_meter: float, height_in_meter: float) -> None:
        self.id = id
        self.type = type
        self.lng = lng
        self.lat = lat
        self.radius_in_meter = radius_in_meter
        self.height_in_meter = height_in_meter


class CuboidZone:

    def __init__(self, id: str, type: str, lng: float, lat: float,
                 length_in_meter: float, width_in_meter: float,
                 height_in_meter: float, rotation: float) -> None:
        self.id = id
        self.type = type
        self.lng = lng
        self.lat = lat
        self.length_in_meter = length_in_meter
        self.width_in_meter = width_in_meter
        self.height_in_meter = height_in_meter
        self.rotation = rotation

class Staff:

    def __init__(self, id: str, lng: float, lat: float, track_at: float,
                 name: str) -> None:
        self.id = id
        self.lng = lng
        self.lat = lat
        self.track_at = track_at
        self.name = name


class SceneAdaptor:

    def __init__(self, device_clicked_handler: Callable[[Dict], None]) -> None:
        self.device_clicked_handler = device_clicked_handler

        self.mq = Queue()
        Thread(target=self.run, daemon=True, name="monitor_adaptor").start()

        self.tracks: Dict[int, List[Track]] = {}
        self.airplanes: Dict[str, Airplane] = {}

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        ws_server = serve(self.serve, "localhost", 9000)
        loop.run_until_complete(ws_server)
        loop.run_forever()
        loop.close()

    async def serve(self, websocket) -> None:
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.001)
            except asyncio.exceptions.TimeoutError:
                pass
            else:
                self.on_message(message)
            try:
                message = self.mq.get_nowait()
            except Empty:
                pass
            else:
                await websocket.send(message)

    def on_message(self, message) -> None:
        message = json.loads(message)
        event = message["event"]
        data = message["data"]
        if event == "deviceClicked":
            self.device_clicked_handler(data)

    def set_center(self, lng: float, lat: float) -> None:
        message = f"""
            let parameter = new AMap.LngLat({lng}, {lat});
            app.$refs.map.map.setCenter(parameter);
        """
        self.mq.put(message)

    def set_zooms(self, zoom_min: float, zoom_max: float) -> None:
        message = f"""
            let parameter = [{zoom_min}, {zoom_max}];
            app.$refs.map.map.setZooms(parameter);
        """
        self.mq.put(message)

    def set_zoom(self, zoom: float) -> None:
        message = f"""
            let parameter = {zoom};
            app.$refs.map.map.setZoom(parameter);
        """
        self.mq.put(message)

    def set_pitch(self, pitch: float) -> None:
        message = f"""
            let parameter = {pitch};
            app.$refs.map.map.setPitch(parameter);
        """
        self.mq.put(message)

    def set_limit_bounds(self, south_west_lng: float, south_west_lat: float,
                         north_east_lng: float, north_east_lat: float) -> None:
        message = f"""
            let parameter =  new AMap.Bounds(
                new AMap.LngLat({south_west_lng}, {south_west_lat}),
                new AMap.LngLat({north_east_lng}, {north_east_lat})
            );
            app.$refs.map.map.setLimitBounds(parameter);
        """
        self.mq.put(message)

    def update_track(self, tracks: List[Track], clear_timeout=5) -> None:
        for track in tracks:
            if track.id not in self.tracks.keys():
                self.tracks[track.id] = []
            self.tracks[track.id].append(track)

        latest_track_at = max(tracks, key=lambda t: t.track_at).track_at
        for id in self.tracks.keys():
            self.tracks[id] = [track for track in self.tracks[id]
                               if latest_track_at - track.track_at <= clear_timeout]
        self.tracks = {k: v for k, v in self.tracks.items() if len(v) > 0}

        def get_parameter() -> str:
            track_lines = []
            for tracks in self.tracks.values():
                positions = []
                heights = []
                for track in tracks:
                    positions.append(
                        f"new AMap.LngLat({track.lng}, {track.lat})")
                    heights.append(f"{track.alt}")
                positions = f"[{', '.join(positions)}]"
                heights = f"[{', '.join(heights)}]"
                track_line = f"""{{
                    positions: {positions},
                    heightsInMeter: {heights},
                    extraInfo: {{
                        type: "{track.type}",
                        size: "{track.size}",
                    }}
                }}"""
                track_lines.append(track_line)
            message = f"[{','.join(track_lines)}]"
            return message

        message = f"""
            let parameter = {get_parameter()};
            let ids = [{",".join([f"'{k}'" for k in self.tracks.keys()])}]
            app.$refs.map.trackLines.show(parameter, ids);
        """
        self.mq.put(message)

    def set_track_marker_visibility(self, visibility: bool) -> None:
        message = f"""
            let parameter = {'true' if visibility else 'false'};
            app.$refs.map.trackLines.setMarkerVisibility(parameter);
        """
        self.mq.put(message)

    def add_or_update_device(self, device: Device) -> None:
        message = f"""
            let parameter = {{
                id: "{device.id}",
                type: "{device.type}",
                position: new AMap.LngLat({device.lng}, {device.lat}),
                extraInfo: {{
                    name: "{device.name}",
                    functional: {"true" if device.functional else "false"},
                }}
            }}
            app.$refs.map.devices.addOrUpdate(parameter);
        """
        self.mq.put(message)

    def set_device_visibility_by_type(self, type: str, visibility: bool) -> None:
        message = f"""
            app.$refs.map.devices.setVisibilityByType(
                "{type}", {"true" if visibility else "false"}
            );
        """
        self.mq.put(message)

    def add_cuboid_zone(self, cuboid_zone: CuboidZone,
                        color: Tuple[float, float, float, float]) -> None:
        deviation = degrees(atan2(cuboid_zone.width_in_meter, cuboid_zone.length_in_meter))
        azimuths = [
            cuboid_zone.rotation - deviation,
            cuboid_zone.rotation + deviation,
            cuboid_zone.rotation + 180 - deviation,
            cuboid_zone.rotation + 180 + deviation,
        ]
        diagonal = sqrt(
            pow(cuboid_zone.length_in_meter, 2) + pow(cuboid_zone.width_in_meter, 2)
        ) / 2
        positions = []
        for i in range(4):
            position = Geodesic.WGS84.Direct(cuboid_zone.lat, cuboid_zone.lng,
                                             azimuths[i], diagonal)
            positions.append((position["lon2"], position["lat2"]))
        positions = f"""[
            new AMap.LngLat({positions[0][0]}, {positions[0][1]}),
            new AMap.LngLat({positions[1][0]}, {positions[1][1]}),
            new AMap.LngLat({positions[2][0]}, {positions[2][1]}),
            new AMap.LngLat({positions[3][0]}, {positions[3][1]}),
        ]"""
        message = f"""
            let cuboid = {{
                id: "{cuboid_zone.id}",
                type: "{cuboid_zone.type}",
                positions: {positions},
                heightInMeter: {cuboid_zone.height_in_meter},
            }}
            let color = [{color[0]}, {color[1]}, {color[2]}, {color[3]}];
            app.$refs.map.zones.addCuboid(cuboid, color);
        """
        self.mq.put(message)

    def add_cylinder_zone(self, cylinder_zone: CylinderZone,
                          color: Tuple[float, float, float, float]) -> None:
        message = f"""
            let cylinder = {{
                id: "{cylinder_zone.id}",
                type: "{cylinder_zone.type}",
                position: new AMap.LngLat({cylinder_zone.lng}, {cylinder_zone.lat}),
                radiusInMeter: {cylinder_zone.radius_in_meter},
                heightInMeter: {cylinder_zone.height_in_meter},
            }}
            let color = [{color[0]}, {color[1]}, {color[2]}, {color[3]}];
            app.$refs.map.zones.addCylinder(cylinder, color);
        """
        self.mq.put(message)

    def set_zone_visibility_by_type_and_id(self, type: str, id: str,
                                           visibility: bool) -> None:
        message = f"""
            app.$refs.map.zones.setVisibilityByTypeAndID(
                "{type}", "{id}",
                {"true" if visibility else "false"}
            );
        """
        self.mq.put(message)

    def add_or_update_staff(self, staff: Staff) -> None:
        message = f"""
            let parameter = {{
                id: "{staff.id}",
                position: new AMap.LngLat({staff.lng}, {staff.lat}),

                extraInfo: {{
                    name: "{staff.name}",
                }}
            }};
            app.$refs.map.staffs.addOrUpdate(parameter);
        """
        self.mq.put(message)

    def set_staff_visibility(self, visibility: bool) -> None:
        message = f"""
            let parameter = {"true" if visibility else "false"};
            app.$refs.map.staffs.setVisibility(parameter);
        """
        self.mq.put(message)

    def update_airplane(self, airplane: Airplane, clear_timeout=10):
        if airplane.id not in self.airplanes.keys():
            self.airplanes[airplane.id] = airplane
            rotate_x = None
            rotate_y = None
            rotate_z = None
        else:
            last = self.airplanes[airplane.id]
            self.airplanes[airplane.id] = airplane
            result = Geodesic.WGS84.Inverse(last.lat, last.lng, airplane.lat, airplane.lng)
            rotate_x = degrees(atan2(airplane.alt - last.alt, result["s12"]))
            rotate_y = None
            rotate_z = result["azi2"]

        latest_track_at = airplane.track_at
        self.airplanes = {k: v for k, v in self.airplanes.items()
                          if latest_track_at - v.track_at <= clear_timeout}

        scale = 40
        airplanesToShow = []
        for airplaneToShow in self.airplanes.values():
            if airplaneToShow.id == airplane.id:
                airplanesToShow.append(f"""{{
                    position: new AMap.LngLat({airplaneToShow.lng}, {airplaneToShow.lat}),
                    heightInMeter: {airplaneToShow.alt},
                    scale: {scale},
                    rotateX: {rotate_x if rotate_x else "null"},
                    rotateY: {rotate_y if rotate_y else "null"},
                    rotateZ: {rotate_z if rotate_z else "null"},

                    extraInfo: {{
                        name: "{airplaneToShow.name}",
                    }}
                }}""")
            else:
                airplanesToShow.append(f"""{{
                    position: new AMap.LngLat({airplaneToShow.lng}, {airplaneToShow.lat}),
                    height: {airplaneToShow.alt},
                    scale: {scale},
                    rotateX: null,
                    rotateY: null,
                    rotateZ: null,

                    extraInfo: {{
                        name: "{airplaneToShow.name}",
                    }}
                }}""")

        message = f"""
            let parameter = [{",".join(airplanesToShow)}];
            app.$refs.map.airplanes.show(parameter);
        """
        self.mq.put(message)


def test():
    from time import sleep
    import random

    def get_random_track():
        west = 113.271213
        south = 23.362449
        east = 113.341422
        north = 23.416018

        id = random.randint(1, 10)
        lng = random.randrange(int(west * 1_000_000),
                               int(east * 1_000_000)) / 1_000_000
        lat = random.randrange(int(south * 1_000_000),
                               int(north * 1_000_000)) / 1_000_000
        alt = random.randint(50, 500)
        track_at = int(time())
        type = random.choice(["drone", "bird"])
        size = random.choice(["small", "intermediate", "large"])

        return Track(id, lng, lat, alt, track_at, type, size)

    scene_adaptor = SceneAdaptor(lambda: print("hi"))

    scene_adaptor.set_center(113.306646, 23.383048)
    sleep(0.5)
    scene_adaptor.set_zooms(8, 16)
    sleep(0.5)
    scene_adaptor.set_zoom(14)
    sleep(0.5)
    scene_adaptor.set_pitch(70)
    sleep(0.5)
    scene_adaptor.set_limit_bounds(
        113.271213, 23.362449, 113.341422, 23.416018)
    sleep(0.5)

    scene_adaptor.add_or_update_device(
        Device("1", "horn", 113.306646, 23.383048, "horn1", True))
    sleep(0.5)
    scene_adaptor.add_or_update_device(
        Device("1", "horn", 113.307646, 23.384048, "horn1", False))
    sleep(0.5)
    scene_adaptor.set_device_visibility_by_type("horn", False)
    sleep(0.5)
    scene_adaptor.set_device_visibility_by_type("horn", True)
    sleep(0.5)

    scene_adaptor.add_cylinder_zone(
        CylinderZone("跑道1", "预警区", 113.2931433608091, 23.39001427231171, 1800, 100),
        (0.8, 0, 0, 0.5))
    sleep(0.5)
    scene_adaptor.add_cuboid_zone(
        CuboidZone("跑道1", "危险区", 113.31768691397997, 23.38354820915081, 3800, 60, 100, 13.6),
        (0, 0.8, 0, 0.5))
    sleep(0.5)
    scene_adaptor.set_zone_visibility_by_type_and_id("预警区", "跑道1", False)
    sleep(1)
    scene_adaptor.set_zone_visibility_by_type_and_id("预警区", "跑道1", True)
    sleep(0.5)

    scene_adaptor.add_or_update_staff(
        Staff("1", 113.302352, 23.405924, time(), "员工1"))
    sleep(0.5)
    scene_adaptor.add_or_update_staff(
        Staff("1", 113.298318, 23.382922, time(), "员工1"))
    sleep(0.5)
    scene_adaptor.add_or_update_staff(
        Staff("2", 113.308102, 23.367401, time(), "员工2"))
    sleep(1)
    scene_adaptor.set_staff_visibility(False)
    sleep(0.5)

    scene_adaptor.update_airplane(
        Airplane("2", 113.317577, 23.394566, 200, time(), "南方航空2"))
    sleep(0.5)
    positions = [
        (113.313181, 23.367334, 200),
        (113.315928, 23.377513, 400),
        (113.317959, 23.384868, 600),
        (113.320491, 23.393707, 800),
        (113.308003, 23.402057, 1000),
    ]
    for position in positions:
        scene_adaptor.update_airplane(
            Airplane("1", position[0], position[1], position[2], time(), "南方航空1"))
        sleep(0.5)

    scene_adaptor.set_track_marker_visibility(False)
    while True:
        tracks = [get_random_track() for i in range(10)]
        scene_adaptor.update_track(tracks)
        sleep(5)

if __name__ == "__main__":
    test()
