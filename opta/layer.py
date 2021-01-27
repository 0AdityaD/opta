from __future__ import annotations

import os
import re
import shutil
import tempfile
from os import path
from typing import Any, Dict, Iterable, List, Optional

import git
import yaml

from opta.blocks import Blocks
from opta.constants import REGISTRY
from opta.plugins.derived_providers import DerivedProviders
from opta.plugins.link_processor import LinkProcessor
from opta.utils import deep_merge, hydrate


class Layer:
    def __init__(
        self,
        meta: Dict[Any, Any],
        blocks_data: List[Any],
        parent: Optional[Layer] = None,
    ):
        self.meta = meta
        self.parent = parent
        if not Layer.valid_name(self.meta["name"]):
            raise Exception(
                "Invalid layer, can only contain lowercase letters, numbers and hyphens!"
            )
        self.blocks = []
        for block_data in blocks_data:
            self.blocks.append(
                Blocks(
                    self.meta["name"],
                    block_data["modules"],
                    block_data.get("backend", "enabled") == "enabled",
                    self.parent,
                )
            )

    @classmethod
    def load_from_yaml(cls, configfile: str) -> Layer:
        if configfile.startswith("git@"):
            print("Loading layer from git...")
            git_url, file_path = configfile.split("//")
            branch = "main"
            if "?" in file_path:
                file_path, file_vars = file_path.split("?")
                res = dict(
                    map(
                        lambda x: (x.split("=")[0], x.split("=")[1]), file_vars.split(",")
                    )
                )
                branch = res.get("ref", branch)
            t = tempfile.mkdtemp()
            # Clone into temporary dir
            git.Repo.clone_from(git_url, t, branch=branch, depth=1)
            conf = yaml.load(open(os.path.join(t, file_path)), Loader=yaml.Loader)
            shutil.rmtree(t)
        elif path.exists(configfile):
            conf = yaml.load(open(configfile), Loader=yaml.Loader)
        else:
            raise Exception(f"File {configfile} not found")
        return cls.load_from_dict(conf)

    @classmethod
    def load_from_dict(cls, conf: Dict[Any, Any]) -> Layer:
        meta = conf.pop("meta")
        for macro_name, macro_value in REGISTRY["macros"].items():
            if macro_name in conf:
                conf.pop(macro_name)
                conf = deep_merge(conf, macro_value)
        blocks_data = conf.get("blocks", [])
        modules_data = conf.get("modules")
        if modules_data is not None:
            blocks_data.append({"modules": modules_data})
        parent = None
        if "parent" in meta:
            parent = cls.load_from_yaml(meta["parent"])
        return cls(meta, blocks_data, parent)

    @staticmethod
    def valid_name(name: str) -> bool:
        pattern = "^[A-Za-z0-9-]*$"
        return bool(re.match(pattern, name))

    def outputs(self, block_idx: Optional[int] = None) -> Iterable[str]:
        ret: List[str] = []
        block_idx = block_idx or len(self.blocks) - 1
        for block in self.blocks[0 : block_idx + 1]:
            ret += block.outputs()
        return ret

    def gen_tf(self, block_idx: int) -> Dict[Any, Any]:
        ret: Dict[Any, Any] = {}
        current_modules = []
        for block in self.blocks[0 : block_idx + 1]:
            current_modules += block.modules
        LinkProcessor().process(current_modules)
        for block in self.blocks[0 : block_idx + 1]:
            ret = deep_merge(block.gen_tf(), ret)
        hydration = deep_merge(
            self.meta.get("variables", {}),
            {
                "parent_name": self.parent.meta["name"]
                if self.parent is not None
                else "nil",
                "layer_name": self.meta["name"],
                "state_storage": self.state_storage(),
            },
        )
        if self.parent is not None:
            hydration = deep_merge(
                hydration, {"parent": self.parent.meta.get("variables", {})}
            )

        return hydrate(ret, hydration)

    def for_child(self) -> bool:
        return self.parent is not None

    def state_storage(self) -> str:
        if "state_storage" in self.meta:
            return self.meta["state_storage"]
        elif self.parent is not None:
            return self.parent.state_storage()
        return f"opta-tf-state-{self.meta['name']}"

    def gen_providers(self, block_idx: int, backend_enabled: bool) -> Dict[Any, Any]:
        ret: Dict[Any, Any] = {"provider": {}}
        providers = self.meta.get("providers", {})
        if self.parent is not None:
            providers = deep_merge(providers, self.parent.meta.get("providers", {}))
        for k, v in providers.items():
            ret["provider"][k] = v
            if k in REGISTRY["backends"]:
                hydration = deep_merge(
                    self.meta.get("variables", {}),
                    {
                        "parent_name": self.parent.meta["name"]
                        if self.parent is not None
                        else "nil",
                        "layer_name": self.meta["name"],
                        "state_storage": self.state_storage(),
                        "provider": v,
                    },
                )
                if self.parent is not None:
                    hydration = deep_merge(
                        hydration, {"parent": self.parent.meta.get("variables", {})}
                    )

                # Add the backend
                if backend_enabled:
                    ret["terraform"] = hydrate(
                        REGISTRY["backends"][k]["terraform"], hydration
                    )

                if self.parent is not None:
                    # Add remote state
                    backend, config = list(
                        REGISTRY["backends"][k]["terraform"]["backend"].items()
                    )[0]
                    ret["data"] = {
                        "terraform_remote_state": {
                            "parent": {
                                "backend": backend,
                                "config": hydrate(
                                    config,
                                    {
                                        "layer_name": self.parent.meta["name"],
                                        "state_storage": self.state_storage(),
                                        "provider": self.parent.meta.get(
                                            "providers", {}
                                        ).get(k, {}),
                                    },
                                ),
                            }
                        }
                    }

        # Add derived providers like k8s from parent
        ret = deep_merge(ret, DerivedProviders(self.parent, is_parent=True).gen_tf())
        # Add derived providers like k8s from own blocks
        ret = deep_merge(
            ret, DerivedProviders(self, is_parent=False).gen_tf(block_idx=block_idx)
        )

        return ret