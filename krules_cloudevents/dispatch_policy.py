# Copyright 2019 The KRules Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Dispatch policy constants for CloudEvents dispatcher middleware.

Controls whether events dispatched to external URLs also trigger local handlers.
"""


class DispatchPolicyConst:
    """
    Constants for dispatcher middleware policies.

    Modern Policies (recommended):
        - DIRECT: Dispatch to external URL only, skip local handlers
        - BOTH: Dispatch to external URL AND execute local handlers

    Legacy Policies (deprecated, for backward compatibility):
        - NEVER: Skip external dispatch (deprecated - just don't pass dispatch_url)
        - DEFAULT: Same as DIRECT (deprecated - use DIRECT explicitly)
        - ALWAYS: Same as BOTH (deprecated - use BOTH explicitly)

    Example:
        from krules_cloudevents import DispatchPolicyConst

        # Send to external URL only (default)
        await emit("event", subject, payload, dispatch_url="https://...")

        # Send to external URL AND local handlers
        await emit(
            "event",
            subject,
            payload,
            dispatch_url="https://...",
            dispatch_policy=DispatchPolicyConst.BOTH
        )
    """

    # Modern policies
    DIRECT = "direct"  # External only
    BOTH = "both"      # External + local

    # Legacy policies (deprecated)
    NEVER = "never"
    DEFAULT = "default"
    ALWAYS = "always"
