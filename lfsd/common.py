#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Common functionality for the whole LFSD package
"""
import json
from pathlib import Path
from subprocess import check_output


def get_configuration_file_path() -> Path:
    """
    Get the path to the configuration file for the LFS simulation

    Returns:
        Path: The path to the configuration file
    """
    lfs_package_share_directory = Path(__file__).absolute().parent  # package directory
    json_path = lfs_package_share_directory / "lfsd_configuration.json"
    if not json_path.is_file():
        raise FileNotFoundError(json_path)
    return json_path


def get_lfs_path() -> Path:
    """
    Get the path where LFS is installed from the configuration file

    Returns:
        Path: The path of the directory where LFS is installed
    """

    config = json.loads(get_configuration_file_path().read_text())
    lfs_path = Path(config["lfs_path"])
    assert lfs_path.is_dir(), f"LFS path is not a directory {lfs_path}."
    return lfs_path


def get_lfs_cfg_txt_path() -> Path:
    "Returns the path to the LFS configuration file"
    path = get_lfs_path() / "cfg.txt"
    assert path.is_file(), f"LFS configuration file not found at {path}"
    return path


def get_wsl2_host_ip_address() -> str:
    """
    Get the IP address of the host machine where WSL2 is running

    Returns:
        str: The IP address of the WSL2 machine
    """
    if not is_wsl2():
        raise ValueError("This function is only available on WSL2 machines")

    text = Path("/etc/resolv.conf").read_text()
    nameserver, ip_address = text.splitlines()[-1].split()
    assert nameserver == "nameserver"
    return ip_address


def is_wsl2() -> bool:
    "Indicates whether the current machine is a WSL2 machine"
    return b"WSL2" in check_output(["uname", "-r"])


def get_machine_ip_address() -> str:
    "Returns the IP address of the current machine"
    return (
        check_output(["ip", "-f", "inet", "addr", "show", "eth0"])
        .decode("utf-8")
        .split("inet")[1]
        .split("/")[0]
        .strip()
    )
