from adapters import ADAPTERS


class AdapterRegistry:
    def __init__(self, page):
        self.page = page

    def detect(self):
        for adapter_cls in sorted(
            ADAPTERS,
            key=lambda cls: cls.priority,
            reverse=True,
        ):
            adapter = adapter_cls(self.page)

            try:
                if adapter.matches():
                    return adapter
            except Exception:
                continue

        return None
