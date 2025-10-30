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

import os
import socket


def get_source():
    """
    Get CloudEvents source identifier.

    Returns source from environment variables in this order:
    1. CE_SOURCE (if set)
    2. K_SERVICE (if running on Knative)
    3. hostname (fallback)
    """
    source = os.environ.get("CE_SOURCE")
    if source is None:
        if "K_SERVICE" in os.environ:
            source = os.environ["K_SERVICE"]
        else:
            source = socket.gethostname()
    return source
