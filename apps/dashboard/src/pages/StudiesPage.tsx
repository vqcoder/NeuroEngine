import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  IconButton,
  Menu,
  MenuItem,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import type { StudyListItem } from '../types';
import { createStudy, createVideo, deleteStudy, fetchStudies } from '../api';

export default function StudiesPage() {
  const [studies, setStudies] = useState<StudyListItem[]>([]);
  const [loading, setLoading] = useState(true);

  // New study dialog
  const [newStudyOpen, setNewStudyOpen] = useState(false);
  const [newStudyName, setNewStudyName] = useState('');
  const [newStudyDescription, setNewStudyDescription] = useState('');
  const [newStudyVideoUrl, setNewStudyVideoUrl] = useState('');
  const [creating, setCreating] = useState(false);

  // Delete confirmation
  const [deleteConfirmStudy, setDeleteConfirmStudy] = useState<StudyListItem | null>(null);

  // Card menu
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [menuStudy, setMenuStudy] = useState<StudyListItem | null>(null);

  const loadStudies = async () => {
    try {
      setLoading(true);
      const items = await fetchStudies();
      setStudies(items);
    } catch (err) {
      console.error('Failed to load studies', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStudies();
  }, []);

  const handleCreate = async () => {
    if (!newStudyName.trim()) return;
    setCreating(true);
    try {
      const study = await createStudy(newStudyName.trim(), newStudyDescription.trim() || undefined);
      // Create a video record so the study is ready to receive submissions
      const videoUrl = newStudyVideoUrl.trim() || undefined;
      await createVideo(study.id, newStudyName.trim(), videoUrl);
      setNewStudyOpen(false);
      setNewStudyName('');
      setNewStudyDescription('');
      setNewStudyVideoUrl('');
      await loadStudies();
    } catch (err) {
      console.error('Failed to create study', err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirmStudy) return;
    try {
      await deleteStudy(deleteConfirmStudy.id);
      setDeleteConfirmStudy(null);
      await loadStudies();
    } catch (err) {
      console.error('Failed to delete study', err);
    }
  };

  return (
    <Box sx={{ bgcolor: '#08080a', minHeight: '100vh', px: 3, py: 4 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography
          variant="h5"
          sx={{ fontFamily: '"DM Sans", sans-serif', fontWeight: 700, color: '#e8e6e3' }}
        >
          Studies
        </Typography>
        <Button
          variant="contained"
          onClick={() => setNewStudyOpen(true)}
          sx={{
            bgcolor: '#c8f031',
            color: '#08080a',
            fontWeight: 700,
            textTransform: 'none',
            '&:hover': { bgcolor: '#b5d82c' },
          }}
        >
          New Study
        </Button>
      </Stack>

      {loading ? (
        <Grid container spacing={2}>
          {[0, 1, 2].map((i) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={i}>
              <Skeleton variant="rectangular" height={160} sx={{ borderRadius: 2, bgcolor: '#1a1a22' }} />
            </Grid>
          ))}
        </Grid>
      ) : studies.length === 0 ? (
        <Typography sx={{ color: '#8a8895', textAlign: 'center', mt: 8 }}>
          No studies yet. Create one to get started.
        </Typography>
      ) : (
        <Grid container spacing={2}>
          {studies.map((study) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={study.id}>
              <Card
                sx={{
                  bgcolor: '#111116',
                  border: '1px solid #26262f',
                  borderRadius: 2,
                  '&:hover': { borderColor: '#3a3a48' },
                }}
              >
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                    <Box
                      component={Link}
                      to={`/studies/${study.id}`}
                      sx={{ textDecoration: 'none', flex: 1, minWidth: 0 }}
                    >
                      <Typography
                        variant="subtitle1"
                        sx={{
                          fontWeight: 700,
                          color: '#e8e6e3',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {study.name}
                      </Typography>
                    </Box>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        setMenuAnchor(e.currentTarget);
                        setMenuStudy(study);
                      }}
                      sx={{ color: '#8a8895' }}
                    >
                      <MoreVertIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                  {study.description && (
                    <Typography
                      variant="body2"
                      sx={{
                        color: '#8a8895',
                        mt: 0.5,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {study.description}
                    </Typography>
                  )}
                  <Stack direction="row" spacing={3} mt={2}>
                    <Box>
                      <Typography variant="caption" sx={{ color: '#6a6878' }}>
                        Videos
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#e8e6e3', fontWeight: 600 }}>
                        {study.video_count}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" sx={{ color: '#6a6878' }}>
                        Sessions
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#e8e6e3', fontWeight: 600 }}>
                        {study.session_count}
                      </Typography>
                    </Box>
                  </Stack>
                  {study.last_activity && (
                    <Typography variant="caption" sx={{ color: '#6a6878', mt: 1, display: 'block' }}>
                      Last activity: {new Date(study.last_activity).toLocaleDateString()}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Card menu */}
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={() => {
          setMenuAnchor(null);
          setMenuStudy(null);
        }}
        slotProps={{ paper: { sx: { bgcolor: '#1a1a22', color: '#e8e6e3' } } }}
      >
        <MenuItem
          onClick={() => {
            if (menuStudy) setDeleteConfirmStudy(menuStudy);
            setMenuAnchor(null);
            setMenuStudy(null);
          }}
          sx={{ color: '#f44336' }}
        >
          Delete
        </MenuItem>
      </Menu>

      {/* New study dialog */}
      <Dialog
        open={newStudyOpen}
        onClose={() => setNewStudyOpen(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{ sx: { bgcolor: '#111116', color: '#e8e6e3' } }}
      >
        <DialogTitle>New Study</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            label="Name"
            fullWidth
            value={newStudyName}
            onChange={(e) => setNewStudyName(e.target.value)}
            sx={{ mt: 1 }}
            InputLabelProps={{ sx: { color: '#8a8895' } }}
            InputProps={{ sx: { color: '#e8e6e3' } }}
          />
          <TextField
            label="Description (optional)"
            fullWidth
            multiline
            rows={2}
            value={newStudyDescription}
            onChange={(e) => setNewStudyDescription(e.target.value)}
            sx={{ mt: 2 }}
            InputLabelProps={{ sx: { color: '#8a8895' } }}
            InputProps={{ sx: { color: '#e8e6e3' } }}
          />
          <TextField
            label="Video URL (optional)"
            placeholder="https://example.com/video.mp4 or leave blank for default"
            fullWidth
            value={newStudyVideoUrl}
            onChange={(e) => setNewStudyVideoUrl(e.target.value)}
            sx={{ mt: 2 }}
            InputLabelProps={{ sx: { color: '#8a8895' } }}
            InputProps={{ sx: { color: '#e8e6e3' } }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewStudyOpen(false)} sx={{ color: '#8a8895' }}>
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!newStudyName.trim() || creating}
            sx={{ color: '#c8f031' }}
          >
            {creating ? 'Creating...' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog
        open={Boolean(deleteConfirmStudy)}
        onClose={() => setDeleteConfirmStudy(null)}
        PaperProps={{ sx: { bgcolor: '#111116', color: '#e8e6e3' } }}
      >
        <DialogTitle>Delete Study</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete &quot;{deleteConfirmStudy?.name}&quot;? This action
            cannot be undone and will remove all associated videos and sessions.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmStudy(null)} sx={{ color: '#8a8895' }}>
            Cancel
          </Button>
          <Button onClick={handleDelete} sx={{ color: '#f44336' }}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
