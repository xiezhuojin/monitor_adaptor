from typing import List, Dict, Tuple, Optional
from threading import Thread
from queue import Queue, Empty
from time import time
import asyncio

import websockets


class Track:

    def __init__(self, id: int, lng: float, lat: float, alt: float, track_at: float,
                 size: str, danger: str) -> None:
        self.id = id
        self.lng = lng
        self.lat = lat
        self.alt = alt
        self.track_at = track_at

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


class Zone:

    def __init__(self, id: str, type: str, path: List[List[Tuple[float, float]]],
                 height: float, color: str) -> None:
        self.id = id
        self.type = type
        self.path = path
        self.height = height
        self.color = color


class Airplane:

    def __init__(self, id: str, lng: float, lat: float, alt: float, scale: float,
                 rotate_x: Optional[float], rotate_y: Optional[float],
                 rotate_z: Optional[float], name: str) -> None:
        self.id = id
        self.lng = lng
        self.lat = lat
        self.alt = alt
        self.scale = scale
        self.rotate_x = rotate_x
        self.rotate_y = rotate_y
        self.rotate_z = rotate_z
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

        ws_server = websockets.serve(self.serve, "localhost", 9000)
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

    def update_center(self, lng: float, lat: float) -> None:
        message = f"""
            let parameter = new AMap.LngLat({lng}, {lat});
            app.$refs.map.map.setCenter(parameter);
        """
        self.mq.put(message)

    def update_zooms(self, zoom_min: float, zoom_max: float) -> None:
        message = f"""
            let parameter = [{zoom_min}, {zoom_max}];
            app.$refs.map.map.setZooms(parameter);
        """
        self.mq.put(message)

    def update_zoom(self, zoom: float) -> None:
        message = f"""
            let parameter = {zoom};
            app.$refs.map.map.setZoom(parameter);
        """
        self.mq.put(message)

    def update_pitch(self, pitch: float) -> None:
        message = f"""
            let parameter = {pitch};
            app.$refs.map.map.setPitch(parameter);
        """
        self.mq.put(message)

    def update_limit_bounds(self, south_west_lng: float, south_west_lat: float,
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
                    positions.append(f"new AMap.LngLat({track.lng}, {track.lat})")
                    heights.append(f"{track.alt}")
                positions = f"[{', '.join(positions)}]"
                heights = f"[{', '.join(heights)}]"
                track_line = f"""{{
                    positions: {positions},
                    heights: {heights},
                    extra_info: {{
                        size: {track.size},
                        danger: {track.danger},
                    }}
                }}"""
                track_lines.append(track_line)
            message = f"[{','.join(track_lines)}]"
            return message

        message = f"""
            let parameter = {get_parameter()};
            let ids = [{",".join([f"'{k}'" for k in self.tracks.keys()])}]
            app.$refs.map.trackLines.updateTracks(parameter, ids);
        """
        self.mq.put(message)

    def update_device(self, device: Device) -> None:
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
            app.$refs.map.devices.updateDevice(parameter);
        """
        self.mq.put(message)

    def set_device_visibility_by_type(self, type: str, visibility: bool) -> None:
        message = f"""
            app.$refs.map.devices.setVisibilityByType(
                "{type}", {"true" if visibility else "false"}
            );
        """
        self.mq.put(message)

    def update_zone(self, zone: Zone) -> None:
        paths = []
        for shape in zone.path:
            path = []
            for s in shape:
                path.append(f"new AMap.LngLat({s[0]}, {s[1]})")
            path = f"[{','.join(path)}]"
            paths.append(path)
        paths = f"[{','.join(paths)}]"

        path = ",".join([f"new AMap.LngLat({p[0]}, {p[1]})" for p in zone.path])
        message = f"""
            let parameter = {{
                id: "{zone.id}",
                type: "{zone.type}",
                path: {paths},
                height: {zone.height},
                color: "{zone.color}",
            }};
            app.$refs.map.zones.updateZone(parameter);
        """
        self.mq.put(message)

    def set_zone_visibility_by_type(self, type: str, visibility: bool) -> None:
        message = f"""
            app.$refs.map.zones.setVisibilityByType(
                "{type}", {"true" if visibility else "false"}
            );
        """
        self.mq.put(message)


if __name__ == "__main__":
    from time import sleep
    import random

    def get_random_track():
        west = 113.271213
        south = 23.362449
        east = 113.341422
        north = 23.416018

        id = random.randint(1, 2)
        lng = random.randrange(int(west * 1_000_000), int(east * 1_000_000)) / 1_000_000
        lat = random.randrange(int(south * 1_000_000), int(north * 1_000_000)) / 1_000_000
        alt = random.randint(50, 5000)
        track_at = int(time())
        size = random.choice(["'小型'", "'中型'", "'大型'"])
        danger = random.choice(["'低威'", "'中威'", "'高威'"])

        return Track(id, lng, lat, alt, track_at, size, danger)

    monitor_adaptor = MonitorAdaptor(lambda: print("hi"))

    monitor_adaptor.update_center(113.306646, 23.383048)
    sleep(0.5)
    monitor_adaptor.update_zooms(8, 16)
    sleep(0.5)
    monitor_adaptor.update_zoom(14)
    sleep(0.5)
    monitor_adaptor.update_pitch(70)
    sleep(0.5)
    monitor_adaptor.update_limit_bounds(113.271213, 23.362449, 113.341422, 23.416018)
    sleep(0.5)
    monitor_adaptor.update_device(Device("1", "horn", 113.306646, 23.383048, "horn1", True))
    sleep(2)
    monitor_adaptor.update_device(Device("1", "horn", 113.307646, 23.384048, "horn1", False))
    sleep(1)
    monitor_adaptor.set_device_visibility_by_type("horn", False)
    sleep(0.5)
    monitor_adaptor.update_zone(Zone("1", "danger",
                                  [[(113.307706,23.3737), (113.315884,23.371746),
                                    (113.314939,23.36729), (113.307043,23.368054)]],
                                  1000, "#0088ffcc"))
    sleep(0.5)
    monitor_adaptor.update_zone(Zone("1", "danger",
                                  [[(113.322407,23.405254), (113.325025,23.40464),
                                    (113.323652,23.400166), (113.316714,23.401668)]],
                                  500, "#0088aacc"))
    sleep(0.5)
    monitor_adaptor.set_zone_visibility_by_type("danger", False)
    sleep(1)
    monitor_adaptor.set_zone_visibility_by_type("danger", True)
    sleep(0.5)

    while True:
        tracks = [get_random_track() for i in range(2)]
        monitor_adaptor.update_track(tracks)
        sleep(1)
