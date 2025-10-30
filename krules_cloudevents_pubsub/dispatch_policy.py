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
Dispatch Policy Constants for PubSub Publisher/Subscriber

Defines how events with 'topic' metadata should be handled by dispatcher middleware.
"""


class DispatchPolicyConst:
    """
    Constants for dispatcher middleware policies.

    Attributes:
        DIRECT: Dispatch to external topic ONLY, skip local handlers
        BOTH: Dispatch to external topic AND execute local handlers
        NEVER: Legacy - skip dispatch, only local handlers (deprecated)
        DEFAULT: Legacy - fallback to DIRECT (deprecated)
        ALWAYS: Legacy - same as BOTH (deprecated)
    """

    # Modern policies (KRules 2.0)
    DIRECT = "direct"  # External only
    BOTH = "both"      # External + local

    # Legacy policies (deprecated, for backward compatibility)
    NEVER = "never"    # Deprecated: don't use topic, just omit it
    DEFAULT = "default"  # Deprecated: ambiguous, use DIRECT or BOTH
    ALWAYS = "always"  # Deprecated: use BOTH instead
