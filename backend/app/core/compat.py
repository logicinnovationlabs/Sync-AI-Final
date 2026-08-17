"""
Compatibility shims for Python 3.12+ and modern packaging environments.
Provides fallback for pkg_resources when setuptools >= 80 removes it.
"""

import sys
import types

def ensure_pkg_resources_compat():
    """Ensure pkg_resources is available for OpenTelemetry instrumentation."""
    try:
        import pkg_resources  # noqa: F401
    except ImportError:
        try:
            import importlib.metadata as importlib_metadata
        except ImportError:
            import importlib_metadata

        pkg_mod = types.ModuleType("pkg_resources")

        class DistributionNotFound(Exception):
            pass

        class RequirementParseError(Exception):
            pass

        class VersionConflict(Exception):
            pass

        class Requirement:
            def __init__(self, spec):
                self.key = str(spec).split()[0].split("=")[0].split("<")[0].split(">")[0].lower()
                self.specs = []

            @classmethod
            def parse(cls, s):
                return cls(s)

        class Distribution:
            def __init__(self, project_name="unknown", version="0.0.0"):
                self.project_name = project_name
                self.key = project_name.lower()
                self.version = version
                self.parsed_version = version

        def get_distribution(dist_name):
            try:
                name = str(dist_name)
                v = importlib_metadata.version(name)
                return Distribution(project_name=name, version=v)
            except Exception:
                return Distribution(project_name=str(dist_name), version="1.0.0")

        def iter_entry_points(group, name=None):
            try:
                eps = importlib_metadata.entry_points()
                if hasattr(eps, "select"):
                    matches = eps.select(group=group)
                else:
                    matches = eps.get(group, [])
                if name:
                    return [ep for ep in matches if ep.name == name]
                return list(matches)
            except Exception:
                return []

        pkg_mod.Distribution = Distribution
        pkg_mod.DistributionNotFound = DistributionNotFound
        pkg_mod.RequirementParseError = RequirementParseError
        pkg_mod.VersionConflict = VersionConflict
        pkg_mod.Requirement = Requirement
        pkg_mod.get_distribution = get_distribution
        pkg_mod.iter_entry_points = iter_entry_points

        sys.modules["pkg_resources"] = pkg_mod

ensure_pkg_resources_compat()
