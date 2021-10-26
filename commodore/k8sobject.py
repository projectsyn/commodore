class K8sObject:
    def __init__(self, obj):
        self._obj = {}
        if obj:
            self._obj = obj
        self._kind = self._obj.get("kind", "")
        self._name = self._obj.get("metadata", {}).get("name", "")
        self._namespace = self._obj.get("metadata", {}).get("namespace", "")

    def __lt__(self, other):
        if self._kind != other._kind:
            return self._kind < other._kind
        if self._namespace != other._namespace:
            return self._namespace < other._namespace
        return self._name < other._name

    def __gt__(self, other):
        if self._kind != other._kind:
            return self._kind > other._kind
        if self._namespace != other._namespace:
            return self._namespace > other._namespace
        return self._name > other._name

    def __eq__(self, other):
        return (
            self._kind == other._kind
            and self._namespace == other._namespace
            and self._name == other._name
        )

    def __le__(self, other):
        return not self.__gt__(other)

    def __ge__(self, other):
        return not self.__lt__(other)

    def __ne__(self, other):
        return not self.__eq__(other)
