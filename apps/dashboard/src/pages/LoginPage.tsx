import { useState } from 'react';
import { Box, Button, Stack, TextField, Typography, Alert } from '@mui/material';
import { supabase } from '../lib/supabase';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!supabase) return;
    setLoading(true);
    setError(null);

    const { error: authError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    setLoading(false);
    if (authError) {
      setError(authError.message);
    }
  };

  const handleForgotPassword = async () => {
    if (!supabase || !email.trim()) {
      setError('Enter your email address first.');
      return;
    }
    setLoading(true);
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim());
    setLoading(false);
    if (resetError) {
      setError(resetError.message);
    } else {
      setResetSent(true);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: '#08080a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Box
        component="form"
        onSubmit={handleSignIn}
        sx={{
          width: '100%',
          maxWidth: 380,
          p: 4,
          bgcolor: '#111116',
          border: '1px solid #26262f',
          borderRadius: 2,
        }}
      >
        <Stack spacing={2.5} alignItems="center">
          <Box
            sx={{
              width: 36,
              height: 36,
              bgcolor: '#c8f031',
              borderRadius: '7px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: '"JetBrains Mono", monospace',
              fontWeight: 700,
              fontSize: 18,
              color: '#08080a',
            }}
          >
            &alpha;
          </Box>
          <Typography
            variant="h6"
            sx={{
              fontFamily: '"DM Sans", sans-serif',
              fontWeight: 700,
              color: '#e8e6e3',
            }}
          >
            Sign in to your account
          </Typography>

          {error && <Alert severity="error" sx={{ width: '100%' }}>{error}</Alert>}
          {resetSent && (
            <Alert severity="success" sx={{ width: '100%' }}>
              Password reset email sent. Check your inbox.
            </Alert>
          )}

          <TextField
            fullWidth
            size="small"
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
          <TextField
            fullWidth
            size="small"
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />

          <Button
            type="submit"
            fullWidth
            variant="contained"
            disabled={loading}
            sx={{ bgcolor: '#c8f031', color: '#08080a', fontWeight: 700, '&:hover': { bgcolor: '#b8e020' } }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </Button>

          <Button
            size="small"
            onClick={handleForgotPassword}
            disabled={loading}
            sx={{ color: '#8a8895', textTransform: 'none', fontSize: '0.8rem' }}
          >
            Forgot password?
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}
