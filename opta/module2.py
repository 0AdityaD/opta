import copy
from typing import Any, Dict, List, Optional

from opta.link import Link


class Module:
    type: str
    links: List[Link]
    input: Dict[str, Any]

    def __init__(self) -> None:
        self.links = []
        self.input = {}
        self._alias: Optional[str] = None

    def __repr__(self) -> str:
        args = {
            "type": self.type,
            "links": self.links,
            "input": self.input,
        }

        if self.alias != self.type:
            args["alias"] = self.alias

        printed_args = ", ".join(
            f"{key}={repr(value)}" for key, value in args.items() if value
        )

        return f"Module({printed_args})"

    @property
    def alias(self) -> str:
        return self._alias or self.type

    @alias.setter
    def alias(self, value: Optional[str]) -> None:
        if value:
            self._alias = value
        else:
            self._alias = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "Module":
        module = cls()
        module.type = raw["type"]

        if "alias" in raw:
            module.alias = raw["alias"]

        module.links = [Link.from_raw(raw_link) for raw_link in raw.get("links", [])]

        input = copy.deepcopy(raw)
        input.pop("type", ...)
        input.pop("links", ...)
        input.pop("alias", ...)
        module.input = input

        return module

    def to_raw(self) -> Dict[str, Any]:
        raw: Dict[str, Any] = {
            "type": self.type,
            "alias": self.alias,
        }

        if self.links:
            raw["links"] = [link.to_raw() for link in self.links]

        if self.input:
            raw["input"] = self.input

        return raw

    def link_for_module(self, module_alias: str) -> Link:
        try:
            return next(link for link in self.links if link.name == module_alias)
        except StopIteration:
            raise KeyError(f"Link to module {module_alias} not found") from None


Module2 = Module