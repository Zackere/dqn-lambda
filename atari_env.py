import gym
from scipy.misc import imresize
import numpy as np
from rllab.envs.gym_env import *


class AtariEnv(GymEnv):
    def __init__(self, env_name, agent_history_length, screen_dims=(84, 84), record_video=True, video_schedule=None, log_dir=None, record_log=True, force_reset=False):
        if log_dir is None:
            if logger.get_snapshot_dir() is None:
                logger.log('Warning: skipping Gym environment monitoring since snapshot_dir not configured.')
            else:
                log_dir = os.path.join(logger.get_snapshot_dir(), 'gym_log')
        Serializable.quick_init(self, locals())

        env = gym.envs.make(env_name)
        self.env = env
        self.env_id = env.spec.id

        assert not (not record_log and record_video)

        if log_dir is None or record_log is False:
            self.monitoring = False
        else:
            if not record_video:
                video_schedule = NoVideoSchedule()
            else:
                if video_schedule is None:
                    video_schedule = CappedCubicVideoSchedule()
            self.env = gym.wrappers.Monitor(self.env, log_dir, video_callable=video_schedule, force=True)
            self.monitoring = True

        self._agent_history_length = agent_history_length
        self._screen_dims = screen_dims
        self._observation_space = self._create_observation_space(env)
        logger.log("observation space: {}".format(self._observation_space))

        self._action_space = convert_gym_space(env.action_space)
        logger.log("action space: {}".format(self._action_space))

        self._horizon = env.spec.tags['wrapper_config.TimeLimit.max_episode_steps']
        self._log_dir = log_dir
        self._force_reset = force_reset

    def reset(self):
        raw_obs = super().reset()
        return self._create_obs_from_raw(raw_obs, reset=True)

    def step(self, action):
        # The superclass returns a namedtuple containing the raw observation from the Atari emulator
        step = super().step(action)

        # We need to replace the raw observation with our observation
        obs = self._create_obs_from_raw(raw_obs=step.observation)
        return step._replace(observation=obs)

    def _create_obs_from_raw(self, raw_obs, reset=False):
        if reset:
            # Reset the history
            self._history = np.zeros(self._history_shape)
        else:
            # Discard the oldest observation
            self._history[:-1] = self._history[1:]

        # Resize the raw observation and append it to the history
        self._history[-1] = self._resize(raw_obs)

        # Return the concatenated history as the observation
        return self._stack_history()

    def _resize(self, obs):
        # Resize the height/width of the observation (if it's an image)
        return imresize(obs, size=self._screen_dims) if not self._obs_is_ram else obs

    def _stack_history(self):
        # The first axis is the length of the history, but we want it to be the last
        history = np.moveaxis(self._history, source=0, destination=-1)

        # Stack the history along the last axis
        return np.concatenate(history, axis=-1)

    def _create_observation_space(self, env):
        shape = list(env.observation_space.shape)

        # If the rank of the observation space is 1, the observations are RAM states of the emulator
        self._obs_is_ram = (len(shape) == 1)

        if not self._obs_is_ram:
            # If the observations are the screen pixels, change the height/width to the given dimensions
            shape[:2] = list(self._screen_dims)

        # This represents the shape of the history buffer:
        self._history_shape = [self._agent_history_length] + list(shape)

        # Multiplying the last axis by the history length gives the final shape of the observation space
        shape[-1] *= self._agent_history_length

        # Create the observation space
        observation_space = gym.spaces.Box(low=0, high=255, shape=shape)
        return convert_gym_space(observation_space)
