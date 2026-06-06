/**
 * diffEngine.ts — Compute unified diffs and detect binary/minified files.
 * Uses the 'diff' npm library (6M+ weekly downloads, compatible with diff-match-patch).
 */

import * as Diff from 'diff';
import * as path from 'path';
import * as fs from 'fs';

const BINARY_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp', '.svg',
  '.pdf', '.zip', '.tar', '.gz', '.rar', '.7z',
  '.exe', '.dll', '.so', '.dylib',
  '.mp3', '.mp4', '.wav', '.mov', '.avi',
  '.ttf', '.otf', '.woff', '.woff2',
  '.sqlite', '.db',
  '.pyc', '.class', '.o',
]);

/**
 * Normalize line endings to LF (critical for Windows — prevents false-positive diffs).
 */
export function normalizeLineEndings(content: string): string {
  return content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

/**
 * Detect if a file is binary by extension or null-byte scan.
 */
export function detectBinary(filePath: string): boolean {
  const ext = path.extname(filePath).toLowerCase();
  if (BINARY_EXTENSIONS.has(ext)) {
    return true;
  }

  // Read first 8KB and check for null bytes
  try {
    const buffer = Buffer.alloc(8192);
    const fd = fs.openSync(filePath, 'r');
    const bytesRead = fs.readSync(fd, buffer, 0, 8192, 0);
    fs.closeSync(fd);
    for (let i = 0; i < bytesRead; i++) {
      if (buffer[i] === 0) {
        return true;
      }
    }
  } catch {
    // If we can't read, assume not binary
  }
  return false;
}

/**
 * Detect minified files by filename pattern.
 */
export function detectMinified(relativePath: string): boolean {
  return relativePath.includes('.min.');
}

/**
 * Compute a unified diff patch between old and new content.
 * Returns null if there are no actual changes.
 * The patch is compatible with Python's diff-match-patch backend.
 */
export function computeDiff(oldContent: string, newContent: string, filePath: string): string | null {
  const normalizedOld = normalizeLineEndings(oldContent);
  const normalizedNew = normalizeLineEndings(newContent);

  if (normalizedOld === normalizedNew) {
    return null; // No changes
  }

  const patch = Diff.createPatch(
    filePath,      // context label (filename shown in diff header)
    normalizedOld,
    normalizedNew,
    '',            // old header
    '',            // new header
  );

  // A patch with no hunks has only 4 header lines — skip it
  const lines = patch.split('\n');
  if (lines.length <= 4) {
    return null;
  }

  return patch;
}
