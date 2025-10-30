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
DEPRECATED: This module location is deprecated in KRules 2.0.0.

Import from krules_cloudevents_pubsub.publisher instead:
    from krules_cloudevents_pubsub.publisher import CloudEventsDispatcher

This backward compatibility import will be removed in a future version.
"""

import warnings

# Backward compatibility import
from ..publisher import CloudEventsDispatcher

warnings.warn(
    "Importing from krules_cloudevents_pubsub.route.dispatcher is deprecated. "
    "Use 'from krules_cloudevents_pubsub.publisher import CloudEventsDispatcher' instead.",
    DeprecationWarning,
    stacklevel=2
)
