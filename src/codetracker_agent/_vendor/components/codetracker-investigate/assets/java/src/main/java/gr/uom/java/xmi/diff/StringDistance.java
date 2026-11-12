package gr.uom.java.xmi.diff;

// Derived from RefactoringMiner 3.0.11 (Nikolaos Tsantalis, MIT).
// See META-INF/LICENSE.RefactoringMiner. Only edit-distance execution is changed:
// exact UTF-16 distances, thresholds and the upstream 1100-character guard remain.

import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import java.util.Arrays;
import java.util.regex.Pattern;

import org.apache.commons.io.IOUtils;

import com.github.difflib.DiffUtils;
import com.github.difflib.patch.AbstractDelta;
import com.github.difflib.patch.Chunk;
import com.github.difflib.patch.Patch;

public class StringDistance {
	private static final int MAX_STRING_LENGTH = 1100;
	private static final ThreadLocal<int[][]> ROWS = ThreadLocal.withInitial(
		() -> new int[][] {new int[MAX_STRING_LENGTH + 1], new int[MAX_STRING_LENGTH + 1]});
	private static final ThreadLocal<long[]> ASCII_MASKS = ThreadLocal.withInitial(() -> new long[128]);
	private static final Pattern COMMENT_LINE = Pattern.compile("^\\s*(//|\\*|import\\s).*");
	
	public static int editDistance(String a, String b, int threshold) {
		int length1 = a.length();
		int length2 = b.length();
		if(length1 > MAX_STRING_LENGTH || length2 > MAX_STRING_LENGTH) {
			return threshold;
		}
		if (threshold < 0) throw new IllegalArgumentException("Threshold must not be negative");
		return distance(a, b, threshold);
	}

	public static int editDistance(String a, String b) {
		int length1 = a.length();
		int length2 = b.length();
		if(length1 > MAX_STRING_LENGTH || length2 > MAX_STRING_LENGTH) {
			return Math.max(length1, length2);
		}
		return distance(a, b, Math.max(length1, length2));
	}

	private static int distance(String a, String b, int threshold) {
		// Equal prefixes/suffixes cancel in unit-cost Levenshtein distance. Keep
		// offsets instead of allocating substrings or boxed character inputs.
		int start = 0, endA = a.length(), endB = b.length();
		while (start < endA && start < endB && a.charAt(start) == b.charAt(start)) start++;
		while (endA > start && endB > start && a.charAt(endA - 1) == b.charAt(endB - 1)) {
			endA--;
			endB--;
		}
		int n = endA - start, m = endB - start;
		if (n > m) {
			String swap = a; a = b; b = swap;
			int length = n; n = m; m = length;
		}
		if (m - n > threshold) return -1;
		if (n == 0) return m;
		if (threshold == 0) return -1; // The equal prefix was already removed.
		if (n >= 8 && n <= Long.SIZE) {
			boolean ascii = true;
			for (int j = 0; j < n; j++) if (a.charAt(start + j) >= 128) { ascii = false; break; }
			if (ascii) return bitDistance(a, b, start, n, m, threshold);
		}
		int[][] rows = ROWS.get();
		int[] previous = rows[0], current = rows[1];
		int infinity = MAX_STRING_LENGTH * 2 + 1;
		Arrays.fill(previous, 0, n + 1, infinity);
		for (int j = 0; j <= Math.min(n, threshold); j++) previous[j] = j;
		for (int i = 1; i <= m; i++) {
			current[0] = i;
			int from = Math.max(1, i - threshold);
			int to = threshold >= n ? n : Math.min(n, i + threshold);
			if (from > 1) current[from - 1] = infinity;
			char right = b.charAt(start + i - 1);
			int minimum = infinity;
			for (int j = from; j <= to; j++) {
				current[j] = a.charAt(start + j - 1) == right ? previous[j - 1]
					: Math.min(previous[j - 1], Math.min(previous[j], current[j - 1])) + 1;
				minimum = Math.min(minimum, current[j]);
			}
			if (minimum > threshold) return -1;
			if (to < n) current[to + 1] = infinity;
			int[] swap = previous; previous = current; current = swap;
		}
		return previous[n] <= threshold ? previous[n] : -1;
	}

	private static int bitDistance(String a, String b, int start, int n, int m, int threshold) {
		// Myers' bit-vector recurrence: each bit represents one DP row. Java's
		// wrapping long arithmetic is intentional, including a 64-character pattern.
		long[] masks = ASCII_MASKS.get();
		Arrays.fill(masks, 0L);
		for (int j = 0; j < n; j++) masks[a.charAt(start + j)] |= 1L << j;
		long positive = -1L, negative = 0L, last = 1L << (n - 1);
		int distance = n;
		for (int i = 0; i < m; i++) {
			char character = b.charAt(start + i);
			long equal = character < 128 ? masks[character] : 0L;
			long vertical = equal | negative;
			long horizontal = (((equal & positive) + positive) ^ positive) | equal;
			long plus = negative | ~(horizontal | positive);
			long minus = positive & horizontal;
			if ((plus & last) != 0) distance++;
			else if ((minus & last) != 0) distance--;
			plus = (plus << 1) | 1L;
			minus <<= 1;
			positive = minus | ~(vertical | plus);
			negative = plus & vertical;
			if (distance - (m - i - 1) > threshold) return -1;
		}
		return distance <= threshold ? distance : -1;
	}

	public static boolean trivialCommentChange(String fileBefore, String fileAfter) throws IOException {
		if(fileBefore.length() == fileAfter.length()) {
			List<String> original = IOUtils.readLines(new StringReader(fileBefore));
			List<String> revised = IOUtils.readLines(new StringReader(fileAfter));

			Patch<String> patch = DiffUtils.diff(original, revised);
			List<AbstractDelta<String>> deltas = patch.getDeltas();
			for(AbstractDelta<String> delta : deltas) {
				Chunk<String> source = delta.getSource();
				if(source.getLines().size() > 0 && !source.getLines().get(0).isBlank() && !COMMENT_LINE.matcher(source.getLines().get(0)).matches()) {
					return false;
				}
				Chunk<String> target = delta.getTarget();
				if(target.getLines().size() > 0 && !target.getLines().get(0).isBlank() && !COMMENT_LINE.matcher(target.getLines().get(0)).matches()) {
					return false;
				}
			}
			return true;
		}
		else {
			List<String> original = IOUtils.readLines(new StringReader(fileBefore));
			List<String> revised = IOUtils.readLines(new StringReader(fileAfter));

			if(original.size() == revised.size()) {
				Patch<String> patch = DiffUtils.diff(original, revised);
				List<AbstractDelta<String>> deltas = patch.getDeltas();
				for(AbstractDelta<String> delta : deltas) {
					Chunk<String> source = delta.getSource();
					if(source.getLines().size() > 0 && !source.getLines().get(0).isBlank() && !COMMENT_LINE.matcher(source.getLines().get(0)).matches()) {
						return false;
					}
					Chunk<String> target = delta.getTarget();
					if(target.getLines().size() > 0 && !target.getLines().get(0).isBlank() && !COMMENT_LINE.matcher(target.getLines().get(0)).matches()) {
						return false;
					}
				}
				return true;
			}
		}
		return false;
	}

	public static boolean isNumeric(String str) {
		for(char c : str.toCharArray()) {
			if(!Character.isDigit(c)) return false;
		}
		return true;
	}
}
