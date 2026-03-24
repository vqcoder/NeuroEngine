import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Box,
  Button,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import type { StudyDetail } from '../types';
import { fetchStudyDetail, updateStudy } from '../api';

export default function StudyDetailPage() {
  const { studyId } = useParams<{ studyId: string }>();
  const [study, setStudy] = useState<StudyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Inline editing
  const [editingName, setEditingName] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);
  const [nameValue, setNameValue] = useState('');
  const [descValue, setDescValue] = useState('');

  const loadStudy = async () => {
    if (!studyId) return;
    try {
      setLoading(true);
      const data = await fetchStudyDetail(studyId);
      setStudy(data);
      setNameValue(data.name);
      setDescValue(data.description ?? '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load study');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStudy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId]);

  const handleSaveName = async () => {
    if (!studyId || !nameValue.trim()) return;
    setEditingName(false);
    try {
      await updateStudy(studyId, { name: nameValue.trim() });
      await loadStudy();
    } catch (err) {
      console.error('Failed to update name', err);
    }
  };

  const handleSaveDesc = async () => {
    if (!studyId) return;
    setEditingDesc(false);
    try {
      await updateStudy(studyId, { description: descValue.trim() || undefined });
      await loadStudy();
    } catch (err) {
      console.error('Failed to update description', err);
    }
  };

  const watchlabBase =
    (import.meta.env.VITE_WATCHLAB_URL as string | undefined)?.replace(/\/+$/, '') ||
    'https://lab.alpha-engine.ai';
  const inviteUrl = study ? `${watchlabBase}${study.participant_invite_path}` : '';

  if (loading) {
    return (
      <Box sx={{ bgcolor: '#08080a', minHeight: '100vh', px: 3, py: 4 }}>
        <Skeleton variant="text" width={300} height={40} sx={{ bgcolor: '#1a1a22' }} />
        <Skeleton variant="rectangular" height={200} sx={{ mt: 2, borderRadius: 2, bgcolor: '#1a1a22' }} />
      </Box>
    );
  }

  if (error || !study) {
    return (
      <Box sx={{ bgcolor: '#08080a', minHeight: '100vh', px: 3, py: 4 }}>
        <Typography sx={{ color: '#f44336' }}>{error ?? 'Study not found'}</Typography>
        <Button component={Link} to="/studies" sx={{ color: '#c8f031', mt: 2 }}>
          Back to Studies
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ bgcolor: '#08080a', minHeight: '100vh', px: 3, py: 4 }}>
      {/* Back link */}
      <Button component={Link} to="/studies" sx={{ color: '#8a8895', mb: 2, textTransform: 'none' }}>
        &larr; All Studies
      </Button>

      {/* Name */}
      {editingName ? (
        <TextField
          autoFocus
          value={nameValue}
          onChange={(e) => setNameValue(e.target.value)}
          onBlur={() => void handleSaveName()}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleSaveName();
            if (e.key === 'Escape') {
              setEditingName(false);
              setNameValue(study.name);
            }
          }}
          fullWidth
          InputProps={{
            sx: {
              color: '#e8e6e3',
              fontSize: '1.5rem',
              fontWeight: 700,
              fontFamily: '"DM Sans", sans-serif',
            },
          }}
          sx={{ mb: 1 }}
        />
      ) : (
        <Typography
          variant="h4"
          onClick={() => setEditingName(true)}
          sx={{
            fontFamily: '"DM Sans", sans-serif',
            fontWeight: 700,
            color: '#e8e6e3',
            cursor: 'pointer',
            '&:hover': { opacity: 0.8 },
            mb: 1,
          }}
        >
          {study.name}
        </Typography>
      )}

      {/* Description */}
      {editingDesc ? (
        <TextField
          autoFocus
          value={descValue}
          onChange={(e) => setDescValue(e.target.value)}
          onBlur={() => void handleSaveDesc()}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setEditingDesc(false);
              setDescValue(study.description ?? '');
            }
          }}
          fullWidth
          multiline
          rows={2}
          InputProps={{ sx: { color: '#8a8895' } }}
          sx={{ mb: 2 }}
        />
      ) : (
        <Typography
          variant="body1"
          onClick={() => setEditingDesc(true)}
          sx={{
            color: '#8a8895',
            cursor: 'pointer',
            '&:hover': { opacity: 0.8 },
            mb: 2,
            minHeight: 24,
          }}
        >
          {study.description || 'Click to add a description...'}
        </Typography>
      )}

      {/* Stats */}
      <Stack direction="row" spacing={4} mb={3}>
        <Box>
          <Typography variant="caption" sx={{ color: '#6a6878' }}>
            Total Sessions
          </Typography>
          <Typography variant="h6" sx={{ color: '#e8e6e3', fontWeight: 700 }}>
            {study.session_count}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" sx={{ color: '#6a6878' }}>
            Completed
          </Typography>
          <Typography variant="h6" sx={{ color: '#e8e6e3', fontWeight: 700 }}>
            {study.completed_session_count}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" sx={{ color: '#6a6878' }}>
            Videos
          </Typography>
          <Typography variant="h6" sx={{ color: '#e8e6e3', fontWeight: 700 }}>
            {study.videos.length}
          </Typography>
        </Box>
      </Stack>

      {/* Invite section */}
      <Box
        sx={{
          bgcolor: '#111116',
          border: '1px solid #26262f',
          borderRadius: 2,
          p: 2,
          mb: 3,
        }}
      >
        <Typography variant="subtitle2" sx={{ color: '#e8e6e3', fontWeight: 700, mb: 1 }}>
          Participant Invite Link
        </Typography>
        <Stack direction="row" spacing={2} alignItems="center">
          <TextField
            value={inviteUrl}
            InputProps={{ readOnly: true, sx: { color: '#8a8895', fontSize: '0.85rem' } }}
            fullWidth
            size="small"
          />
          <Button
            variant="outlined"
            size="small"
            onClick={() => {
              void navigator.clipboard.writeText(inviteUrl);
            }}
            sx={{ color: '#c8f031', borderColor: '#c8f031', textTransform: 'none', whiteSpace: 'nowrap' }}
          >
            Copy
          </Button>
        </Stack>
        {inviteUrl && (
          <Box sx={{ mt: 2 }}>
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=${encodeURIComponent(inviteUrl)}`}
              alt="QR code for invite link"
              width={120}
              height={120}
              style={{ borderRadius: 4 }}
            />
          </Box>
        )}
      </Box>

      {/* Videos table */}
      <Typography variant="subtitle1" sx={{ color: '#e8e6e3', fontWeight: 700, mb: 1 }}>
        Videos ({study.videos.length})
      </Typography>
      {study.videos.length === 0 ? (
        <Typography sx={{ color: '#8a8895' }}>No videos in this study yet.</Typography>
      ) : (
        <TableContainer
          sx={{
            bgcolor: '#111116',
            border: '1px solid #26262f',
            borderRadius: 2,
          }}
        >
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ color: '#6a6878', borderColor: '#26262f' }}>Title</TableCell>
                <TableCell sx={{ color: '#6a6878', borderColor: '#26262f' }}>Sessions</TableCell>
                <TableCell sx={{ color: '#6a6878', borderColor: '#26262f' }}>Completed</TableCell>
                <TableCell sx={{ color: '#6a6878', borderColor: '#26262f' }}>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {study.videos.map((video) => (
                <TableRow key={video.video_id} hover sx={{ '&:hover': { bgcolor: '#1a1a22' } }}>
                  <TableCell sx={{ borderColor: '#26262f' }}>
                    <Box
                      component={Link}
                      to={`/videos/${video.video_id}`}
                      sx={{ color: '#c8f031', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
                    >
                      {video.title}
                    </Box>
                  </TableCell>
                  <TableCell sx={{ color: '#e8e6e3', borderColor: '#26262f' }}>
                    {video.sessions_count}
                  </TableCell>
                  <TableCell sx={{ color: '#e8e6e3', borderColor: '#26262f' }}>
                    {video.completed_sessions_count}
                  </TableCell>
                  <TableCell sx={{ color: '#8a8895', borderColor: '#26262f' }}>
                    {new Date(video.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
