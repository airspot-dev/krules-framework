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
KRules 2.0 Event Types

In KRules 2.0, event types are plain strings (no EventType wrapper needed).
The decorators @on() accept strings directly.
"""

# Built-in event types (emitted automatically by the Subject system)
SUBJECT_PROPERTY_CHANGED = SubjectPropertyChanged = "subject-property-changed"
SUBJECT_PROPERTY_DELETED = SubjectPropertyDeleted = "subject-property-deleted"
SUBJECT_DELETED = SubjectDeleted = "subject-deleted"

# Legacy alias (deprecated in 2.0.0)
SUBJECT_FLUSHED = SubjectFlushed = "subject-deleted"  # Renamed: flush() deletes the subject
