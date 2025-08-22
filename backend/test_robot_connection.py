#!/usr/bin/env python

"""Test script to debug robot connection issues"""

import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_robot_connection():
    """Test robot connection with detailed error reporting"""
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    robot_type = os.getenv("ROBOT_TYPE", "so100_follower")
    robot_port = os.getenv("ROBOT_PORT", "/dev/ttyACM0")
    
    print(f"Testing robot connection...")
    print(f"Robot Type: {robot_type}")
    print(f"Robot Port: {robot_port}")
    
    # Check if port exists
    if not Path(robot_port).exists():
        print(f"ERROR: Port {robot_port} does not exist!")
        print("Available serial ports:")
        import glob
        for port in glob.glob("/dev/tty*"):
            if "ACM" in port or "USB" in port:
                print(f"  - {port}")
        return
    
    # Try to import and connect
    try:
        from lerobot.robots import make_robot_from_config
        from lerobot.robots.so100_follower.config_so100_follower import SO100FollowerConfig
        
        print(f"Creating SO100 robot config...")
        
        # Create config for SO100
        robot_config = SO100FollowerConfig(
            port=robot_port,
            cameras={},  # No cameras for testing
            id="andrej",  # Use andrej as robot ID
            use_degrees=False,
            disable_torque_on_disconnect=True
        )
        
        print(f"Creating robot instance using make_robot_from_config...")
        robot = make_robot_from_config(robot_config)
        
        print("Connecting to robot...")
        robot.connect()
        
        print("SUCCESS: Robot connected!")
        
        # Test getting observation
        print("Getting observation...")
        obs = robot.get_observation()
        print(f"Observation keys: {obs.keys()}")
        
        # Disconnect
        robot.disconnect()
        print("Robot disconnected successfully")
        
    except ImportError as e:
        print(f"ERROR: Could not import robot module: {e}")
        print("Make sure lerobot is installed with the correct robot support")
        
    except PermissionError as e:
        print(f"ERROR: Permission denied accessing port {robot_port}")
        print("Try running with sudo or add user to dialout group:")
        print(f"  sudo usermod -a -G dialout $USER")
        print("Then logout and login again")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_robot_connection()