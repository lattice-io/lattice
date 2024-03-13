#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

from copy import deepcopy
import logging
import os
import time
import abc
from dataclasses import dataclass
from concurrent.futures._base import Future
from concurrent.futures.thread import ThreadPoolExecutor
import re
from threading import Event, Lock
from typing import Dict, List, TextIO, Optional

from urllib import request

# Prometheus
from prometheus_client import CollectorRegistry, Gauge
from prometheus_client import push_to_gateway


log = logging.getLogger(__name__)


METRICS_TAG = r'''\[LATTICE METRICS\]'''


PrometheusBackend = 'prometheus'
METRICS_PUSHGATEWAY_BACKENDS = [PrometheusBackend]

# <metric_name_in_addon:metric_name_in_monitoring_system>
METRICS_MAPPING = {
    "world_size": "lattice_agent_monitor_world_size"
}


@dataclass
class MetricPublisherConfig:
    backend: str
    endpoint: str
    job_id: str


class MetricPublisher(abc.ABC):
    def __init__(self, config: MetricPublisherConfig):
        self._config = config
        self._init_publisher()

    @abc.abstractmethod
    def _init_publisher(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def push(self, metrics):
        raise NotImplementedError()


class PrometheusMetricPublisher(MetricPublisher):
    def _init_publisher(self):
        self._registry = CollectorRegistry()
        self._metrics: Dict[str, Gauge] = {}
        self._labels: Dict[str, str] = {
            'job_id': self._config.job_id
        }
        self._metric_job_name = f"lattice-agent-monitor-{self._config.job_id}"

    def push(self, metrics):
        need_push = False
        for k, v in metrics.items():
            if METRICS_MAPPING.get(k, None) is None:
                continue

            if k not in self._metrics:
                self._metrics[k] = Gauge(METRICS_MAPPING[k], "", registry=self._registry)
            self._metrics[k].set(v)
            need_push = True

        if need_push:
            try:
                push_to_gateway(self._config.endpoint,
                                job=self._metric_job_name, registry=self._registry)
            except Exception:
                log.info(f"Pushing to gateway using config {self._config} failed")


class LogMonitor:
    """
    Monitors the given log files for metrics. The log files do not have to
    exist when the ``start()`` method is called. The tail-er will gracefully
    wait until the log files are created by the producer and will tail the
    contents of the log files until the ``stop()`` method is called.

    .. warning:: ``LogMonitor`` will wait indefinitely for the log file to be created!

    Each log file's line will be suffixed with a header of the form: ``[{name}{idx}]:``,
    where the ``name`` is user-provided and ``idx`` is the index of the log file
    in the ``log_files`` mapping.

    Usage:

    ::

     log_files = {0: "/tmp/0_stdout.log", 1: "/tmp/1_stdout.log"}
     monitor = LogMonitor("trainer", log_files, sys.stdout).start()
     # actually run the trainers to produce 0_stdout.log and 1_stdout.log
     run_trainers()
     tailer.stop()

     # once run_trainers() start writing the ##_stdout.log files
     # the tailer will print to sys.stdout:
     # >>> [trainer0]:log_line1
     # >>> [trainer1]:log_line1
     # >>> [trainer0]:log_line2
     # >>> [trainer0]:log_line3
     # >>> [trainer1]:log_line2

    .. note:: Due to buffering log lines between files may not necessarily
              be printed out in order. You should configure your application's
              logger to suffix each log line with a proper timestamp.

    """

    def __init__(
        self,
        name: str,
        log_files: Dict[int, str],
        dst: TextIO,
        interval_sec: float = 0.1,
        monitor_config: Dict[str, str] = {}
    ):
        n = len(log_files)
        self._threadpool = None
        if n > 0:
            self._threadpool = ThreadPoolExecutor(
                max_workers=n,
                thread_name_prefix=f"{self.__class__.__qualname__}_{name}",
            )

        self._name = name
        self._dst = dst
        self._log_files = log_files
        self._finished_events: Dict[int, Event] = {
            local_rank: Event() for local_rank in log_files.keys()
        }
        self._futs: List[Future] = []
        self._interval_sec = interval_sec
        self._stopped = False
        self._lock = Lock()
        self._metrics_list: List = []
        self._metrics_pattern = re.compile(METRICS_TAG)
        self._metric_publisher: Optional[MetricPublisher] = self._init_pushgateway(monitor_config)

    def _init_pushgateway(self, monitor_config):
        def _reachable(url):
            try:
                code = request.urlopen(url, timeout=5).getcode()
                if code != 200:
                    raise Exception("Connection failed")
            except Exception:
                log.info(f"Connection to {url} failed")
                return False
            return True

        def _get_valid_config(config: Dict[str, str]) -> Optional[MetricPublisherConfig]:
            backend = monitor_config.get('metric_pushgateway_backend', "")
            endpoint = monitor_config.get('metric_pushgateway_endpoint', "")
            job_id = monitor_config.get('metric_pushgateway_job_id', "")

            if backend not in METRICS_PUSHGATEWAY_BACKENDS:
                log.info(f'Invalid metric pushgateway backend {backend}')
                return None

            if len(endpoint) <= 0:
                log.info('Empty metric pushgateway endpoint')
                return None

            if len(job_id) <= 0:
                log.info('Empty metric pushgateway job id')
                return None

            if not _reachable(f"http://{endpoint}"):
                log.info(f'Metric pushgateway endpoint {endpoint} is not reachable')
                return None

            return MetricPublisherConfig(
                backend=backend,
                endpoint=endpoint,
                job_id=job_id)

        config = _get_valid_config(monitor_config)
        if config is not None:
            log.info(f"Get valid monitor config {config}")
            publishers = {
                PrometheusBackend: PrometheusMetricPublisher
            }
            return publishers.get(config.backend, lambda _: None)(config)

        log.info(f"Get invalid monitor config {monitor_config}")
        return None

    def get_log_files(self):
        return self._log_files

    def get_log_file(self, local_rank):
        return self._log_files[local_rank]

    def get_metrics(self):
        with self._lock:
            metrics_copy = deepcopy(self._metrics_list)
            self._metrics_list.clear()
            return metrics_copy

    def _add_metrics(self, metrics):
        with self._lock:
            self._metrics_list.append(metrics)
            if self._metric_publisher is not None:
                self._metric_publisher.push(metrics)

    def _parse_metrics(self, metrics_str):
        metrics = {}
        try:
            for m in metrics_str.split(','):
                name, value = m.strip().split(':')
                metrics[name] = value
        except Exception:
            pass

        return metrics

    def monitor_log_file(
        self, header: str, file: str, dst: TextIO, finished: Event, interval_sec: float
    ):
        while not os.path.exists(file):
            if finished.is_set():
                return
            time.sleep(interval_sec)

        with open(file, "r") as fp:
            while True:
                line = fp.readline()

                match = self._metrics_pattern.search(line)
                if match:
                    metrics = self._parse_metrics(line[match.end():])
                    log.info(f'Get metric {metrics}')
                    self._add_metrics(metrics)

                    continue

                if line:
                    dst.write(f"{header}{line}")
                else:  # reached EOF
                    if finished.is_set():
                        # log line producer is finished
                        break
                    else:
                        # log line producer is still going
                        # wait for a bit before looping again
                        time.sleep(interval_sec)

    def start(self) -> "LogMonitor":
        if not self._threadpool:
            return self

        for local_rank, file in self._log_files.items():
            self._futs.append(
                self._threadpool.submit(
                    self.monitor_log_file,
                    header=f"[{self._name}{local_rank}]:",
                    file=file,
                    dst=self._dst,
                    finished=self._finished_events[local_rank],
                    interval_sec=self._interval_sec,
                )
            )
        return self

    def stop(self) -> None:
        for finished in self._finished_events.values():
            finished.set()

        for local_rank, f in enumerate(self._futs):
            try:
                f.result()
            except Exception as e:
                log.error(
                    f"error in log tailor for {self._name}{local_rank}."
                    f" {e.__class__.__qualname__}: {e}",
                )

        if self._threadpool:
            self._threadpool.shutdown(wait=True)

        self._stopped = True

    def stopped(self) -> bool:
        return self._stopped
