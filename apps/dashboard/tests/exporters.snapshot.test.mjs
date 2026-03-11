import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readoutPayloadSchema } from '../src/schemas/readoutPayload.js';
import {
  buildEditSuggestionsStubPayload,
  buildReadoutCsv,
  buildReadoutJsonPayload
} from '../src/utils/exporters.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FIXED_GENERATED_AT = '2026-03-06T00:00:00.000Z';

function loadReadoutFixture() {
  const fixturePath = path.resolve(__dirname, '../../../fixtures/readout_payload.sample.json');
  return readoutPayloadSchema.parse(JSON.parse(readFileSync(fixturePath, 'utf-8')));
}

test('per-timepoint CSV export matches snapshot fixture', () => {
  const readout = loadReadoutFixture();
  const csv = buildReadoutCsv(readout, ['AU04', 'AU06', 'AU12'], {
    generatedAt: FIXED_GENERATED_AT
  });
  const expectedPath = path.resolve(__dirname, 'fixtures/readout_export_snapshot.csv');
  const expected = readFileSync(expectedPath, 'utf-8').trimEnd();
  assert.equal(csv.trimEnd(), expected);
});

test('JSON exports (readout + edit suggestions stub) match snapshot fixture', () => {
  const readout = loadReadoutFixture();
  const snapshot = {
    readout_json: buildReadoutJsonPayload(readout, { generatedAt: FIXED_GENERATED_AT }),
    edit_suggestions_stub: buildEditSuggestionsStubPayload(readout, {
      generatedAt: FIXED_GENERATED_AT
    })
  };
  const expectedPath = path.resolve(__dirname, 'fixtures/readout_export_snapshot.json');
  const expected = JSON.parse(readFileSync(expectedPath, 'utf-8'));
  assert.deepEqual(snapshot, expected);
});

test('export payload metadata is present and dopamine key is not emitted', () => {
  const readout = loadReadoutFixture();
  const readoutJson = buildReadoutJsonPayload(readout, { generatedAt: FIXED_GENERATED_AT });
  const editSuggestions = buildEditSuggestionsStubPayload(readout, { generatedAt: FIXED_GENERATED_AT });

  assert.equal(readoutJson.schema_version, '1.0.0');
  assert.equal(readoutJson.metadata.video_id, readout.video_id);
  assert.equal(editSuggestions.schema_version, '1.0.0');
  assert.equal(editSuggestions.metadata.video_id, readout.video_id);

  const serialized = JSON.stringify({ readout_json: readoutJson, edit_suggestions_stub: editSuggestions });
  assert.equal(serialized.includes('"dopamine"'), false);
});
