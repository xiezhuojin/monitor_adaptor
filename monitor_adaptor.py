from typing import List, Dict
from threading import Thread
from queue import Queue, Empty
from time import time
import asyncio

from websockets import serve


class Track:

    def __init__(self, id: int, lng: float, lat: float, alt: float, track_at: float,
                 type: str, size: str, danger: str) -> None:
        self.id = id
        self.lng = lng
        self.lat = lat
        self.alt = alt
        self.track_at = track_at

        self.type = type
        self.size = size
        self.danger = danger


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


class MonitorAdaptor:

    def __init__(self, device_clicked_handler: callable([[object, object], None])) -> None:
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
        print(message)

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
                    heights: {heights},
                    extraInfo: {{
                        type: "{track.type}",
                        size: "{track.size}",
                        danger: "{track.danger}",
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

    def add_cuboid_zone(self, cuboid_zone: CuboidZone) -> None:
        message = f"""
            let parameter = {{
                id: "{cuboid_zone.id}",
                type: "{cuboid_zone.type}",
                position: new AMap.LngLat({cuboid_zone.lng}, {cuboid_zone.lat}),
                lengthInMeter: {cuboid_zone.length_in_meter},
                widthInMeter: {cuboid_zone.width_in_meter},
                heightInMeter: {cuboid_zone.height_in_meter},
                rotation: {cuboid_zone.rotation},
            }}
            app.$refs.map.zones.addCuboid(parameter);
        """
        self.mq.put(message)

    def add_cylinder_zone(self, cylinder_zone: CylinderZone) -> None:
        message = f"""
            let parameter = {{
                id: "{cylinder_zone.id}",
                type: "{cylinder_zone.type}",
                position: new AMap.LngLat({cylinder_zone.lng}, {cylinder_zone.lat}),
                radiusInMeter: {cylinder_zone.radius_in_meter},
                heightInMeter: {cylinder_zone.height_in_meter},
            }}
            app.$refs.map.zones.addCylinder(parameter);
        """
        self.mq.put(message)

    def toggle_zones_visibility_by_types_and_ids(
            self, types: List[str], ids: List[str], visibility: bool
        ) -> None:
        message = f"""
            app.$refs.map.zones.toggleZonesVisibilityByTypesAndIds(
                [{",".join([f"'{type}'" for type in types])}],
                [{",".join([f"'{id}'" for id in ids])}],
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

    def toggle_staff_visibility(self, visibility: bool) -> None:
        message = f"""
            let parameter = {"true" if visibility else "false"};
            app.$refs.map.staffs.toggleVisibility(parameter);
        """
        self.mq.put(message)

    def update_airplane(self, airplane: Airplane, clear_timeout=5):
        if airplane.id not in self.airplanes.keys():
            self.airplanes[airplane.id] = airplane
            rotate_x = None
            rotate_y = None
            rotate_z = None
        else:
            last = self.airplanes[airplane.id]
            self.airplanes[airplane.id] = airplane
            rotate_x = 1
            rotate_y = 2
            rotate_z = 3

        latest_track_at = airplane.track_at
        self.airplanes = {k: v for k, v in self.airplanes.items()
                          if latest_track_at - v.track_at <= clear_timeout}

        scale = 1000
        airplanesToShow = []
        for airplaneToShow in self.airplanes.values():
            if airplaneToShow.id == airplane.id:
                airplanesToShow.append(f"""{{
                    position: new AMap.LngLat({airplaneToShow.lng}, {airplaneToShow.lat}),
                    height: {airplaneToShow.alt},
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
        alt = random.randint(50, 5000)
        track_at = int(time())
        type = random.choice(["无人机", "鸟"])
        size = random.choice(["小型", "中型", "大型"])
        danger = random.choice(["低威", "中威", "高威"])

        return Track(id, lng, lat, alt, track_at, type, size, danger)

    monitor_adaptor = MonitorAdaptor(lambda: print("hi"))

    monitor_adaptor.set_center(113.306646, 23.383048)
    sleep(0.5)
    monitor_adaptor.set_zooms(8, 16)
    sleep(0.5)
    monitor_adaptor.set_zoom(14)
    sleep(0.5)
    monitor_adaptor.set_pitch(70)
    sleep(0.5)
    monitor_adaptor.set_limit_bounds(
        113.271213, 23.362449, 113.341422, 23.416018)
    sleep(0.5)

    monitor_adaptor.add_or_update_device(
        Device("1", "horn", 113.306646, 23.383048, "horn1", True))
    sleep(0.5)
    monitor_adaptor.add_or_update_device(
        Device("1", "horn", 113.307646, 23.384048, "horn1", False))
    sleep(0.5)
    monitor_adaptor.set_device_visibility_by_type("horn", False)
    sleep(0.5)
    monitor_adaptor.set_device_visibility_by_type("horn", True)
    sleep(0.5)

    monitor_adaptor.add_cylinder_zone(CylinderZone("跑道1", "预警区", 113.306646, 23.383048, 10000, 2000))
    sleep(0.5)
    monitor_adaptor.add_cuboid_zone(CuboidZone("跑道1", "危险区", 113.306646, 23.383048, 3000, 60, 100, 19))
    sleep(0.5)
    monitor_adaptor.toggle_zones_visibility_by_types_and_ids(["预警区",], ["跑道1"], False)
    sleep(1)
    monitor_adaptor.toggle_zones_visibility_by_types_and_ids(["预警区",], ["跑道1"], True)
    sleep(0.5)

    monitor_adaptor.add_or_update_staff(
        Staff("1", 113.302352, 23.405924, time(), "员工1"))
    sleep(0.5)
    monitor_adaptor.add_or_update_staff(
        Staff("1", 113.298318, 23.382922, time(), "员工1"))
    sleep(0.5)
    monitor_adaptor.add_or_update_staff(
        Staff("2", 113.308102, 23.367401, time(), "员工2"))
    sleep(1)
    monitor_adaptor.toggle_staff_visibility(False)
    sleep(0.5)

    # monitor_adaptor.update_airplane(
    #     Airplane("1", 113.299038, 23.405184, 200, time(), "南方航空1"))
    # monitor_adaptor.update_airplane(
    #     Airplane("2", 113.317577, 23.394566, 200, time(), "南方航空2"))
    # sleep(2)
    # monitor_adaptor.update_airplane(
    #     Airplane("1", 113.295948, 23.39362, 200, time(), "南方航空1"))

    while True:
        tracks = [get_random_track() for i in range(10)]
        monitor_adaptor.update_track(tracks)
        sleep(1)

if __name__ == "__main__":
    test()
