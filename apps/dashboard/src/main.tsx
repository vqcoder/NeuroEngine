import React from 'react';
import ReactDOM from 'react-dom/client';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles.css';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#c8f031',
      contrastText: '#08080a'
    },
    secondary: {
      main: '#4a9eff'
    },
    error: {
      main: '#ff6b6b'
    },
    warning: {
      main: '#ffb347'
    },
    success: {
      main: '#c8f031'
    },
    divider: '#26262f',
    text: {
      primary: '#e8e6e3',
      secondary: '#8a8895'
    },
    background: {
      default: '#08080a',
      paper: '#0e0e12'
    }
  },
  shape: {
    borderRadius: 10
  },
  typography: {
    fontFamily: '"DM Sans", "Segoe UI", sans-serif',
    h1: {
      fontFamily: '"DM Sans", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em'
    },
    h2: {
      fontFamily: '"DM Sans", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em'
    },
    h3: {
      fontFamily: '"DM Sans", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em'
    },
    h4: {
      fontFamily: '"DM Sans", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em'
    },
    h5: {
      fontFamily: '"DM Sans", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em'
    },
    h6: {
      fontFamily: '"DM Sans", sans-serif',
      fontWeight: 600,
      letterSpacing: '-0.01em'
    },
    button: {
      fontFamily: '"JetBrains Mono", monospace',
      fontSize: '0.72rem',
      letterSpacing: '0.07em',
      textTransform: 'uppercase'
    }
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: '#08080a',
          color: '#e8e6e3'
        }
      }
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid #26262f'
        }
      }
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: '#141419',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          overflow: 'hidden'
        }
      }
    },
    MuiCardContent: {
      styleOverrides: {
        root: {
          position: 'relative'
        }
      }
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          borderColor: '#26262f'
        },
        outlined: {
          background: 'rgba(255,255,255,0.02)'
        },
        containedPrimary: {
          boxShadow: '0 0 0 1px rgba(200,240,49,0.32)',
          '&:hover': {
            boxShadow: '0 0 24px rgba(200,240,49,0.18)'
          }
        }
      }
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: '0.7rem',
          letterSpacing: '0.03em',
          // Only apply dark background and border to chips with no specific color
          '&:not(.MuiChip-colorPrimary):not(.MuiChip-colorSecondary):not(.MuiChip-colorSuccess):not(.MuiChip-colorError):not(.MuiChip-colorWarning):not(.MuiChip-colorInfo)': {
            backgroundColor: '#1a1a21',
            border: '1px solid #26262f',
            color: '#e8e6e3'
          }
        },
        colorPrimary: {
          backgroundColor: '#c8f031',
          color: '#08080a',
          border: 'none',
          '&:hover': { backgroundColor: '#d4f54a' }
        },
        colorSuccess: {
          backgroundColor: 'rgba(200,240,49,0.15)',
          color: '#c8f031',
          border: '1px solid rgba(200,240,49,0.3)'
        },
        colorWarning: {
          backgroundColor: 'rgba(240,184,96,0.15)',
          color: '#f0b860',
          border: '1px solid rgba(240,184,96,0.3)'
        },
        colorError: {
          backgroundColor: 'rgba(240,104,104,0.15)',
          color: '#f06868',
          border: '1px solid rgba(240,104,104,0.3)'
        },
        colorInfo: {
          backgroundColor: 'rgba(90,173,255,0.15)',
          color: '#5aadff',
          border: '1px solid rgba(90,173,255,0.3)'
        }
      }
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          border: '1px solid #26262f'
        }
      }
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          '& fieldset': {
            borderColor: '#26262f'
          },
          '&:hover fieldset': {
            borderColor: 'rgba(200,240,49,0.4)'
          },
          '&.Mui-focused fieldset': {
            borderColor: '#c8f031'
          }
        }
      }
    },
    MuiInputLabel: {
      styleOverrides: {
        root: {
          '&.Mui-focused': {
            color: '#c8f031'
          }
        }
      }
    }
  }
});

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
);
