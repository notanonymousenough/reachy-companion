# Public pollen-robotics/reachy_mini daemon.py _setup_backend, unchanged.
# https://raw.githubusercontent.com/pollen-robotics/reachy_mini/main/src/reachy_mini/daemon/daemon.py
# Official whole source SHA256 646ddfc085bb035ff57d251cb9b9e1cfb90142b9491a597db849dd467ec0f98f.
# Fixture has no imports, constructors, serial access or real backend bindings.
class Daemon:
    def _setup_backend(
        self,
        wireless_version: bool,
        sim: bool,
        mockup_sim: bool,
        serialport: str,
        scene: str,
        check_collision: bool,
        kinematics_engine: str,
        headless: bool,
        use_audio: bool,
        hardware_config_filepath: str | None = None,
        reflash_motors_on_start: bool = True,
    ) -> "RobotBackend | MujocoBackend | MockupSimBackend":
        if mockup_sim:
            return MockupSimBackend(
                check_collision=check_collision,
                kinematics_engine=kinematics_engine,
                use_audio=use_audio,
            )
        elif sim:
            return MujocoBackend(
                scene=scene,
                check_collision=check_collision,
                kinematics_engine=kinematics_engine,
                headless=headless,
                use_audio=use_audio,
            )
        else:
            if serialport == "auto":
                ports = find_serial_port(wireless_version=wireless_version)

                if len(ports) == 0:
                    raise RuntimeError(
                        "No Reachy Mini serial port found. "
                        "Check USB connection and permissions. "
                        "Or directly specify the serial port using --serialport."
                    )
                elif len(ports) > 1:
                    raise RuntimeError(
                        f"Multiple Reachy Mini serial ports found {ports}. "
                        "Please specify the serial port using --serialport."
                    )

                serialport = ports[0]
                self.logger.info(f"Found Reachy Mini serial port: {serialport}")

            self.logger.info(
                f"Creating RobotBackend with parameters: serialport={serialport}, check_collision={check_collision}, kinematics_engine={kinematics_engine}"
            )

            if reflash_motors_on_start:
                reflash_motors_if_needed(serialport, dont_light_up=True)

            return RobotBackend(
                serialport=serialport,
                log_level=self.log_level,
                check_collision=check_collision,
                kinematics_engine=kinematics_engine,
                use_audio=use_audio,
                wireless_version=wireless_version,
                hardware_config_filepath=hardware_config_filepath,
            )
