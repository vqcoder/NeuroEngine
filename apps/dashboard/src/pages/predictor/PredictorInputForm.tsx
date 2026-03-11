import { FormEvent, useRef } from 'react';
import {
  Box,
  Button,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import LinkIcon from '@mui/icons-material/Link';

export type PredictorInputFormProps = {
  inputTab: 'url' | 'file';
  onInputTabChange: (tab: 'url' | 'file') => void;
  videoUrl: string;
  onVideoUrlChange: (value: string) => void;
  selectedFile: File | null;
  onSelectedFileChange: (file: File | null) => void;
  loading: boolean;
  onSubmit: (event: FormEvent) => void;
  onClearError: () => void;
};

export default function PredictorInputForm({
  inputTab,
  onInputTabChange,
  videoUrl,
  onVideoUrlChange,
  selectedFile,
  onSelectedFileChange,
  loading,
  onSubmit,
  onClearError
}: PredictorInputFormProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  return (
    <Box component="form" onSubmit={onSubmit}>
      <Stack spacing={1.5}>
        <Tabs
          value={inputTab}
          onChange={(_e, v) => { onInputTabChange(v); onClearError(); }}
          sx={{ minHeight: 36, '& .MuiTab-root': { minHeight: 36, py: 0.5, fontSize: '0.78rem' } }}
        >
          <Tab value="url" label="URL" icon={<LinkIcon fontSize="small" />} iconPosition="start" />
          <Tab value="file" label="Upload file" icon={<UploadFileIcon fontSize="small" />} iconPosition="start" />
        </Tabs>

        {inputTab === 'url' ? (
          <Stack spacing={1}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.25}>
              <TextField
                label="Video URL"
                fullWidth
                value={videoUrl}
                onChange={(event) => onVideoUrlChange(event.target.value)}
                placeholder="https://www.ispot.tv/ad/... or https://cdn.example.com/video.mp4"
                helperText="The video will be downloaded, analyzed, and saved to your catalog."
                inputProps={{ 'data-testid': 'predictor-video-url-input' }}
              />
              <Button
                type="submit"
                variant="contained"
                disabled={loading}
                data-testid="predictor-submit"
                sx={{ flexShrink: 0, alignSelf: 'flex-start', mt: '2px' }}
              >
                Predict &amp; store
              </Button>
            </Stack>
          </Stack>
        ) : (
          <Stack spacing={1}>
            <input
              ref={fileInputRef}
              type="file"
              accept="video/mp4,video/quicktime,video/webm,video/x-m4v,.mp4,.mov,.webm,.m4v"
              style={{ display: 'none' }}
              data-testid="predictor-file-input"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                onSelectedFileChange(f);
                onClearError();
              }}
            />
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.25} alignItems="center">
              <Box
                onClick={() => fileInputRef.current?.click()}
                sx={{
                  flex: 1,
                  border: '2px dashed',
                  borderColor: selectedFile ? 'primary.main' : '#26262f',
                  borderRadius: 2,
                  p: 2.5,
                  cursor: 'pointer',
                  textAlign: 'center',
                  transition: 'border-color .2s',
                  '&:hover': { borderColor: 'primary.main' }
                }}
              >
                <UploadFileIcon sx={{ color: selectedFile ? 'primary.main' : 'text.secondary', mb: 0.5 }} />
                <Typography variant="body2" color={selectedFile ? 'primary' : 'text.secondary'}>
                  {selectedFile ? selectedFile.name : 'Click to choose a video file'}
                </Typography>
                {selectedFile ? (
                  <Typography variant="caption" color="text.secondary">
                    {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                  </Typography>
                ) : (
                  <Typography variant="caption" color="text.secondary" display="block">
                    MP4, MOV, WebM — max ~500 MB
                  </Typography>
                )}
              </Box>
              <Button
                type="submit"
                variant="contained"
                disabled={loading || !selectedFile}
                data-testid="predictor-submit-file"
                sx={{ flexShrink: 0 }}
              >
                Predict reactions
              </Button>
            </Stack>
          </Stack>
        )}
      </Stack>
    </Box>
  );
}
