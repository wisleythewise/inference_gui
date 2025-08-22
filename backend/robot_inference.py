#!/usr/bin/env python

import logging
import time
import torch
import gc
from pathlib import Path
from typing import Optional, Dict

from lerobot.cameras import CameraConfig
from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.utils import build_dataset_frame
from lerobot.policies.factory import make_policy
from lerobot.robots import make_robot_from_config
from lerobot.robots.so100_follower.config_so100_follower import SO100FollowerConfig
from lerobot.utils.control_utils import predict_action
from lerobot.utils.robot_utils import busy_wait
from lerobot.utils.utils import get_safe_torch_device

logger = logging.getLogger(__name__)


class RobotInferenceManager:
    def __init__(self, robot_config: Optional[Dict] = None):
        self.current_model = None
        self.current_color = None
        self.policy = None
        self.dataset = None
        self.device = None
        self.robot = None
        self.robot_config = robot_config
        
        self.models = {
            "white": "JaspervanLeuven/pick_cube_place_grey_tray",
            "yellow": "JaspervanLeuven/pick_yellow_box_place_grey_tray_day",
            "black": "JaspervanLeuven/pick_cube_place_grey_tray",
        }
        
        self.tasks = {
            "white": "Pick the white cube",
            "yellow": "Pick the yellow cube",
            "black": "Pick the black cube",
        }
        
        if robot_config:
            self._init_robot()
    
    def _init_robot(self):
        """Initialize the robot from config"""
        try:
            if self.robot_config:
                # Create SO100FollowerConfig object from dict config
                port = self.robot_config.get("port", "/dev/ttyACM0")
                cameras_dict = self.robot_config.get("cameras", {})
                robot_id = self.robot_config.get("id", "andrej")  # Use andrej as default ID
                
                # Convert camera configs to proper OpenCVCameraConfig objects
                from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
                cameras = {}
                for cam_name, cam_config in cameras_dict.items():
                    if isinstance(cam_config, dict):
                        cameras[cam_name] = OpenCVCameraConfig(
                            index_or_path=cam_config.get("index_or_path"),
                            width=cam_config.get("width", 640),
                            height=cam_config.get("height", 480),
                            fps=cam_config.get("fps", 30)
                        )
                    else:
                        cameras[cam_name] = cam_config  # Already a config object
                
                logger.info(f"Creating SO100 robot config: port={port}, cameras={list(cameras.keys())}, id={robot_id}")
                
                # Create the config object for SO100
                robot_config = SO100FollowerConfig(
                    port=port,
                    cameras=cameras,
                    id=robot_id,
                    use_degrees=False,  # Use normalized range -100 to 100
                    disable_torque_on_disconnect=True
                )
                
                # Use make_robot_from_config as the inference script does
                self.robot = make_robot_from_config(robot_config)
                self.robot.connect()
                logger.info("SO100 robot connected successfully")
        except Exception as e:
            logger.warning(f"Could not initialize robot: {e}")
            import traceback
            traceback.print_exc()
            logger.info("Running in simulation mode without real robot")
            self.robot = None
    
    def load_model(self, color: str):
        """Load a specific model, unloading the previous one if necessary"""
        if self.current_color == color and self.policy is not None:
            logger.info(f"Model for {color} already loaded")
            return
        
        logger.info(f"Loading model for {color} boxes")
        
        # Unload current model to free GPU memory
        self.unload_current_model()
        
        model_path = self.models[color]
        
        try:
            # Load dataset metadata
            self.dataset = LeRobotDataset(
                repo_id=model_path,
                root=None,  # Uses default cache
            )
            
            # Load policy configuration
            policy_config = PreTrainedConfig.from_pretrained(model_path)
            policy_config.pretrained_path = model_path
            
            # Create policy with dataset metadata
            self.policy = make_policy(policy_config, ds_meta=self.dataset.meta)
            self.device = get_safe_torch_device(policy_config.device)
            
            # Reset policy state
            self.policy.reset()
            self.current_color = color
            
            logger.info(f"Successfully loaded model for {color} boxes")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def unload_current_model(self):
        """Unload the current model and free GPU memory"""
        if self.policy is not None:
            logger.info(f"Unloading current model ({self.current_color})")
            del self.policy
            self.policy = None
            
        if self.dataset is not None:
            del self.dataset
            self.dataset = None
            
        self.current_color = None
        
        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        
        logger.info("GPU memory cleared")
    
    def execute_pick(self, color: str, duration_s: float = 10.0, fps: int = 30, use_amp: bool = False):
        """
        Execute a pick operation for the specified color
        
        Args:
            color: "white" or "yellow"
            duration_s: Duration to run the pick operation
            fps: Control frequency
            use_amp: Use automatic mixed precision for faster inference
        """
        # Load the appropriate model
        self.load_model(color)
        
        task = self.tasks[color]
        logger.info(f"Executing pick for {color} box: {task}")
        
        if self.robot is None:
            # Simulation mode - just wait and return success
            logger.info("Running in simulation mode (no real robot connected)")
            time.sleep(2)  # Simulate pick operation
            return {
                "success": True,
                "color": color,
                "task": task,
                "mode": "simulation",
                "timestamp": time.time()
            }
        
        # Real robot execution
        try:
            # Reset policy for new episode
            self.policy.reset()
            
            # Get dataset features for formatting
            dataset_features = self.dataset.features
            
            start_time = time.perf_counter()
            timestamp = 0
            actions_executed = 0
            
            while timestamp < duration_s:
                start_loop_t = time.perf_counter()
                
                # Get observation from robot
                observation = self.robot.get_observation()
                
                # Log observation keys for debugging
                if actions_executed == 0:
                    logger.info(f"Observation keys: {list(observation.keys())}")
                    logger.info(f"Dataset features: {list(dataset_features.keys())}")
                
                # Format observation for policy
                observation_frame = build_dataset_frame(
                    dataset_features, 
                    observation, 
                    prefix="observation"
                )
                
                # Predict action using policy
                action_values = predict_action(
                    observation_frame,
                    self.policy,
                    self.device,
                    use_amp,
                    task=task,
                    robot_type=self.robot.robot_type if self.robot else "simulation",
                )
                
                # Convert action tensor to dictionary
                action = {
                    key: action_values[i].item() 
                    for i, key in enumerate(self.robot.action_features)
                }
                
                # Send action to robot
                self.robot.send_action(action)
                actions_executed += 1
                
                # Maintain target FPS
                dt_s = time.perf_counter() - start_loop_t
                busy_wait(1 / fps - dt_s)
                
                timestamp = time.perf_counter() - start_time
            
            logger.info(f"Pick operation completed. Executed {actions_executed} actions")
            
            return {
                "success": True,
                "color": color,
                "task": task,
                "mode": "real",
                "actions_executed": actions_executed,
                "duration": timestamp,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Error during pick execution: {e}")
            return {
                "success": False,
                "color": color,
                "task": task,
                "error": str(e),
                "timestamp": time.time()
            }
    
    def cleanup(self):
        """Clean up resources"""
        self.unload_current_model()
        if self.robot:
            self.robot.disconnect()
            logger.info("Robot disconnected")