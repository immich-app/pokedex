# Talos

Machine config is committed as plain Talos documents and merged per node with
`talosctl machineconfig patch`, later layers winning. Control planes and workers
get different layers:

| Layer                    | Applies to                                                                                    |
| ------------------------ | --------------------------------------------------------------------------------------------- |
| `cluster.yaml`           | every node                                                                                    |
| `controlplane.yaml`      | control-plane nodes only (brock, surge, misty)                                                |
| `secrets.yq`             | control-plane nodes: the talhelper secret bundle from 1Password, reshaped into a patch        |
| `secrets-worker.yq`      | worker nodes: the reduced secret subset (no etcd / service-account / aggregator keys)         |
| `nodes/<node>.yaml`      | one node: `machine.type`, install disk and image, hostname, link aliases, bond, address       |
| `schematics/<node>.yaml` | the Image Factory customization behind that node's installer image                            |

The secret bundle stays in 1Password (`op://Pokedex/talsecret.yaml/talsecret.yaml`),
the same item talhelper used; `secrets.yq` / `secrets-worker.yq` reshape it into a
machine-config patch. `machine.ca` and `cluster.ca` merge as a cert-plus-key unit.

`machine.type` lives in each `nodes/<node>.yaml` and selects which layers apply:
`controlplane` pulls in `controlplane.yaml` + the full secret bundle, anything else
gets the worker subset. Control planes are static (bond0 + address); workers are DHCP
(hostname only). misty pins `install.grubUseUKICmdline: false` because it boots GRUB.

## Tasks (mise)

- `mise run talos:render <node>` — render a node's full machine config to stdout
- `mise run talos:apply-node <node> [args]` — render and `apply-config` to that node (targets its InternalIP; append `--dry-run` to preview)
- `mise run talos:apply [args]` — apply to every node
- `mise run talos:schematic` — print each node's Image Factory schematic ID (paste into `nodes/<node>.yaml`'s `install.image` when a schematic changes)

Version bumps (Talos, Kubernetes) are tuppr's job; a schematic change needs a
reinstall from the new installer image (`talosctl upgrade -i <image> -m powercycle`).
