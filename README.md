# Blackbox Exporter Operator For Machines
This charm operates the Prometheus Blackbox Exporter on bare metal, VMs, machines, LXD, etc.
Prometheus Blackbox Exporter is a monitoring tool that probes external endpoints over protocols like HTTP, HTTPS, DNS, TCP, ICMP, and gRPC to assess their availability, performance, and health from an external perspective.

## What does this charm do?
As an operator for Blackbox Exporter on Juju, this charm automates the lifecycle and provides some functionalities out of the box. This charm is a subordinate charm - that means, it needs to be related to a principal charm and it will scale up and down along with that principal charm. Also, for the purpose of scraping `probe_success` metrics, it's required that there is an Opentelemetry Collector machine charm on every machine with a Blackbox Exporter unit and the BE and Opentelemetry Collector units are related.

> Note that instead of Opentelemetry Collector, you may also use Grafana Agent or any other charm that implements the `CosAgentConsumer` class. 

This charm offers:
1. Automatic cross-unit connectivity checks between all machines hosting a Blackbox Exporter unit. The Juju config option `automatic_connectivity_checks`, with a default of `True`, controls this behaviour. When enabled, each unit of Blackbox Exporter attempts to test its connectivity to _all_ of its peers over _all_ networks. For this reason, each unit creates Prometheus-compatible scrape jobs where the targets are the addresses of all of the other BE units across different network interfaces. This option relies on the `ICMP` module to perform these checks.
2. A `probes_file` config option which allows an admin to provide their own Prometheus-compatible scrape jobs. The charm will then forward these scrape jobs over the `cos_agent` interface to the charm scraping it e.g. Opentelemetry Collector.
3. A `config_file` config option which allows an admin to specify their desired probing modules and parameters in YAML format. By default, this charm uses the following modules which should meet most probing needs. If at any point more complex probes are needed, they can be supplied through this option. Upon providing a value, basic validation will be performed and the charm will be set to `Blocked` if the config is deemed invalid.
```yaml
modules:
    http_2xx:
        prober: http
        timeout: 10s
    tcp_connect:
        prober: tcp
        timeout: 10s
    icmp:
        prober: icmp
        timeout: 10s
        icmp:
            preferred_ip_protocol: "ip4"
            ip_protocol_fallback: true
```

## What does a sample deployment look like?
The exercise below walks you through what a typical set up for this charm looks like. Ensure you have Juju installed and bootstrap a LXD cloud. Then, deploy the following bundle.

```yaml
default-base: ubuntu@24.04/stable
applications:
  be:
    charm: local:blackbox-exporter-operator-0
  otel:
    charm: opentelemetry-collector
    channel: 2/edge
    revision: 148
  ubuntu:
    charm: ubuntu
    channel: latest/stable
    revision: 26
    num_units: 2
    to:
    - "0"
    - "1"
    constraints: arch=amd64
    storage:
      block: loop,100M
      files: rootfs,100M
machines:
  "0":
    constraints: arch=amd64
  "1":
    constraints: arch=amd64
relations:
- - ubuntu:juju-info
  - be:juju-info
- - ubuntu:juju-info
  - otel:juju-info

```
Now, you can use the `probes_file` config option to provide some customs you are interested in probing.
Do `juju config be probes_file=@probes.yaml` where `probes.yaml` is:
```
scrape_configs:
  - job_name: blackbox-http
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
          - https://charmhub.io
          - https://ubuntu.com
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115
```

Assuming you have COS Lite deployed in a K8s model, you can create an offer from your Prometheus. 
For example, do `juju offer prometheus:receive-remote-write`.
In your LXD model containing the deployment above, do `juju consume <k8s-controller-name>:admin/<cos-lite-model-name>.prometheus` and `juju integrate otel prometheus`. Now Opentelemetry Collector will remote write the time-series containing the probe results into Prometheus.
You can now go to the Prometheus Graphs page and enter the query `probe_success`. The results for all the probing BE has done will be there.
> Note: for this exercise you just need the Prometheus charm on K8s. You don't need to have the entire COS Lite solution deployed.

[Blackbox Exporter]: https://github.com/prometheus/blackbox_exporter
