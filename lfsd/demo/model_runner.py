#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
This is a demo of the LFSInterface. It prints the number of visible cones and sends a steering command to LFS.
"""


import pickle
from itertools import count
from pathlib import Path

import numpy as np
from sklearn.neighbors import KernelDensity

from lfsd import ConeTypes, LFSData, LFSInterface


def convert_cones_to_heatmap(cones: np.ndarray, range: int, resolution: int):
    # create a grid of points to evaluate the kde model
    r = np.linspace(-range, range, resolution)

    xx, yy = np.meshgrid(r, r)

    return_value = np.zeros_like(xx)

    for cone_type in [ConeTypes.BLUE, ConeTypes.YELLOW]:
        kde = KernelDensity(bandwidth=0.6)
        kde.fit(cones[cones[:, 2] == cone_type][:, :2])

        # evaluate the kde model on the grid
        zz = np.exp(kde.score_samples(np.c_[xx.ravel(), yy.ravel()]))
        zz = zz.reshape(xx.shape)

        zz[zz < 0.001] = 0

        sign_of_value = -1 if cone_type == ConeTypes.BLUE else 1

        return_value += sign_of_value * zz

    return return_value


def convert_list_of_lfs_data_to_dataset(dataraw: list[LFSData]):
    dataset = []

    for d in dataraw[::]:
        cones = d.processed_outsim_data.visible_cones

        cones_array = np.array(
            [
                (c.x, c.y, c.cone_type)
                for c in cones
                if c.cone_type in [ConeTypes.BLUE, ConeTypes.YELLOW]
            ]
        )

        heatmap = convert_cones_to_heatmap(cones_array, 20, 40)
        heatmap_flat = heatmap.flatten()

        # get car inputs
        steering_angle = d.raw_outsim_data.car_inputs.steering
        throttle = d.raw_outsim_data.car_inputs.throttle
        brake = d.raw_outsim_data.car_inputs.brake

        outputs = np.array([steering_angle, throttle, brake])

        dataset.append((heatmap_flat, outputs))

    return dataset


class MLPLFSInterface(LFSInterface):
    async def on_lfs_data(self, data):
        i = next(self.counter)

        if i % 20 != 0:
            return

        heatmap, _ = convert_list_of_lfs_data_to_dataset([data])[0]

        # normalize the data
        heatmap = self.normalizer([heatmap])

        # predict driving inputs
        from time import time

        tic = time()
        steering, throttle, brake = self.model.predict(heatmap)[0].round(3)

        # overwrite throttle and brake if velocity is low
        if data.processed_outsim_data.linear_velocity_local[0] < 2.0:
            throttle = 0.3
            brake = 0.0

        # overwrite throttle if velocity is high
        if data.processed_outsim_data.linear_velocity_local[0] > 10.0:
            throttle = 0.0

        steering /= -0.52358

        steering = np.clip(steering, -1, 1)
        throttle = np.clip(throttle, 0, 1)
        brake = np.clip(brake, 0, 1)

        toc = time()
        print("prediction took", toc - tic, "seconds")
        print(steering, throttle, brake)
        await self.send_driving_command(steering, throttle, brake)


if __name__ == "__main__":
    interface = MLPLFSInterface()

    # load model stored in model.pkl

    path = Path(__file__).absolute().parent.parent.parent / "model.pkl"

    with open(path, "rb") as f:
        minval, maxval, model = pickle.load(f)

    print(minval, maxval)

    normalzer = lambda x: (x - minval) / (maxval - minval)

    interface.model = model
    interface.normalizer = normalzer
    interface.counter = count()
    interface.spin()
