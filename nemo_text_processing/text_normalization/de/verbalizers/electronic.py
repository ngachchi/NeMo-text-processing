# Copyright (c) 2021, NVIDIA CORPORATION & AFFILIATES.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pynini
from pynini.lib import pynutil

from nemo_text_processing.text_normalization.de.utils import get_abs_path
from nemo_text_processing.text_normalization.en.graph_utils import (
    NEMO_ALPHA,
    NEMO_NOT_QUOTE,
    NEMO_SIGMA,
    NEMO_SPACE,
    GraphFst,
    delete_preserve_order,
    insert_space,
)


class ElectronicFst(GraphFst):
    """
    Finite state transducer for verbalizing electronic
        e.g. electronic { username: "abc" domain: "hotmail.com" } -> "a b c at hotmail punkt com"
                                                           -> "a b c at h o t m a i l punkt c o m"
                                                           -> "a b c at hotmail punkt c o m"
                                                           -> "a b c at h o t m a i l punkt com"
    Args:
        deterministic: if True will provide a single transduction option,
        for False multiple transduction are generated (used for audio-based normalization)
    """

    def __init__(self, deterministic: bool = True):
        super().__init__(name="electronic", kind="verbalize", deterministic=deterministic)
        graph_digit_no_zero = pynini.invert(
            pynini.string_file(get_abs_path("data/numbers/digit.tsv"))
        ).optimize() | pynini.cross("1", "eins")
        graph_zero = pynini.invert(pynini.string_file(get_abs_path("data/numbers/zero.tsv"))).optimize()
        graph_digit = graph_digit_no_zero | graph_zero
        graph_symbols = pynini.string_file(get_abs_path("data/electronic/symbols.tsv")).optimize()
        server_common = pynini.string_file(get_abs_path("data/electronic/server_name.tsv"))
        domain_common = pynini.string_file(get_abs_path("data/electronic/domain.tsv"))

        def add_space_after_char():
            return pynini.closure(NEMO_NOT_QUOTE - pynini.accep(" ") + insert_space) + (
                NEMO_NOT_QUOTE - pynini.accep(" ")
            )

        verbalize_characters = pynini.cdrewrite(graph_symbols | graph_digit, "", "", NEMO_SIGMA)

        user_name = pynutil.delete('username: "') + add_space_after_char() + pynutil.delete('"')
        user_name @= verbalize_characters

        convert_defaults = (pynutil.add_weight(NEMO_NOT_QUOTE, weight=0.0001) | server_common) | domain_common
        domain = convert_defaults + pynini.closure(insert_space + convert_defaults)
        domain @= verbalize_characters

        domain = pynutil.delete('domain: "') + domain + pynutil.delete('"')
        protocol = (
            pynutil.delete('protocol: "')
            + add_space_after_char() @ pynini.cdrewrite(graph_symbols, "", "", NEMO_SIGMA)
            + pynutil.delete('"')
        )
        self.graph = (pynini.closure(protocol + NEMO_SPACE, 0, 1) + domain) | (
            user_name + NEMO_SPACE + pynutil.insert("at ") + domain | (pynutil.insert("at ") + user_name)
        )

        # normalizes sentence-final periods following URLs
        delete_tokens = self.delete_tokens(self.graph + delete_preserve_order)
        preserve_final_period = pynini.cdrewrite(pynini.cross(" punkt", "."), "", "[EOS]", NEMO_SIGMA)

        delete_tokens = delete_tokens @ preserve_final_period
        self.fst = delete_tokens.optimize()
