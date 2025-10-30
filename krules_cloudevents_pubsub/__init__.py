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
KRules CloudEvents PubSub Integration

Provides publisher and subscriber for Google Cloud PubSub with CloudEvents format.
Enables transparent event handling across services using KRules EventBus.

Key components:
- CloudEventsDispatcher: Publisher that sends events to PubSub topics
- PubSubSubscriber: Subscriber that receives events and routes to local EventBus
- Middleware: Transparent publishing via ctx.emit(..., topic="...")

For usage examples, see README.md in this directory.
"""

from .publisher import CloudEventsDispatcher
from .subscriber import PubSubSubscriber, create_subscriber
from .middleware import create_dispatcher_middleware
from .dispatch_policy import DispatchPolicyConst

__all__ = [
    "CloudEventsDispatcher",
    "PubSubSubscriber",
    "create_subscriber",
    "create_dispatcher_middleware",
    "DispatchPolicyConst",
]
