import unittest

class VirtualScrollSimulator:
    def __init__(self, total_items, row_height, view_height):
        self.total_items = total_items
        self.row_height = row_height
        self.view_height = view_height
        self.overscan = 20
        self.scroll_top = 0
        
        # DOM elements simulation
        self.top_spacer_height = 0
        self.bottom_spacer_height = 0
        self.viewport_height = 0
        
        # Optimization state
        self.render_start = -1
        self.render_end = -1

    @property
    def total_height(self):
        return self.top_spacer_height + self.viewport_height + self.bottom_spacer_height

    @property
    def max_scroll_top(self):
        return max(0, self.total_height - self.view_height)

    def render(self, scroll_top, fix_height=False):
        """
        Simulate renderVirtual logic.
        If fix_height is True, we simulate the fix where we reserve viewport height before clearing.
        Returns a list of scroll_top values observed during the process (before, during clear, after).
        """
        self.scroll_top = scroll_top
        
        # Logic from main.js
        start = max(0, int(scroll_top / self.row_height) - self.overscan)
        end = min(self.total_items, int((scroll_top + self.view_height) / self.row_height) + self.overscan)
        
        # Update spacers
        self.top_spacer_height = start * self.row_height
        self.bottom_spacer_height = (self.total_items - end) * self.row_height
        
        # Simulate clearing viewport
        # Before clearing, if fix_height is enabled, we set min-height
        reserved_height = 0
        if fix_height:
            reserved_height = (end - start) * self.row_height
            self.viewport_height = reserved_height # Placeholder
        else:
            self.viewport_height = 0 # Cleared!
            
        # Check clamping during clear
        current_max_scroll = self.max_scroll_top
        clamped_scroll_top = min(self.scroll_top, current_max_scroll)
        
        # Simulate populating viewport
        actual_viewport_height = (end - start) * self.row_height
        self.viewport_height = actual_viewport_height # Populated
        
        return {
            'original_scroll_top': scroll_top,
            'clamped_scroll_top': clamped_scroll_top,
            'final_max_scroll': self.max_scroll_top,
            'did_clamp': clamped_scroll_top < scroll_top
        }

class TestVirtualScroll(unittest.TestCase):
    def test_scroll_clamping_bug(self):
        """
        Test that without the fix, scroll_top is clamped when near bottom.
        """
        sim = VirtualScrollSimulator(total_items=1000, row_height=20, view_height=400)
        
        # Total height = 1000 * 20 = 20000.
        # Max scroll = 20000 - 400 = 19600.
        
        # User scrolls to 19500 (near bottom)
        result = sim.render(19500, fix_height=False)
        
        # Check logic:
        # start = 19500/20 - 20 = 975 - 20 = 955.
        # end = (19500+400)/20 + 20 = 995 + 20 = 1000 (min 1000).
        # top_spacer = 955 * 20 = 19100.
        # bottom_spacer = 0.
        # viewport (cleared) = 0.
        # Total height during clear = 19100 + 0 + 0 = 19100.
        # Max scroll during clear = 19100 - 400 = 18700.
        # Input scroll_top 19500 > 18700.
        # So it should clamp to 18700.
        
        print(f"\n[Bug Repro] Input: 19500 -> Clamped: {result['clamped_scroll_top']}")
        self.assertTrue(result['did_clamp'], "ScrollTop should have been clamped due to height collapse")
        self.assertEqual(result['clamped_scroll_top'], 18700, "Should clamp to max scrollable height during collapse")

    def test_scroll_fix(self):
        """
        Test that WITH the fix (reserving height), scroll_top is preserved.
        """
        sim = VirtualScrollSimulator(total_items=1000, row_height=20, view_height=400)
        
        # Same scenario
        result = sim.render(19500, fix_height=True)
        
        print(f"\n[Fix Verify] Input: 19500 -> Clamped: {result['clamped_scroll_top']}")
        self.assertFalse(result['did_clamp'], "ScrollTop should NOT be clamped when height is reserved")
        self.assertEqual(result['clamped_scroll_top'], 19500, "ScrollTop should remain unchanged")

if __name__ == '__main__':
    unittest.main()
