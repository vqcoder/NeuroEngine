'use client';

export interface StudySurveyProps {
  surveyOverallEngagement: string;
  surveyContentClarity: string;
  surveyAdditionalComments: string;
  canFinishSession: boolean;
  setSurveyOverallEngagement: (value: string) => void;
  setSurveyContentClarity: (value: string) => void;
  setSurveyAdditionalComments: (value: string) => void;
  finishAndUpload: () => void;
}

export default function StudySurvey({
  surveyOverallEngagement,
  surveyContentClarity,
  surveyAdditionalComments,
  canFinishSession,
  setSurveyOverallEngagement,
  setSurveyContentClarity,
  setSurveyAdditionalComments,
  finishAndUpload
}: StudySurveyProps) {
  return (
    <section className="survey-immersive" data-testid="survey-stage">
      <div className="survey-hero-text">
        <h2>Almost done!</h2>
        <p>Rate your experience, then add any thoughts below.</p>
      </div>

      <div className="survey-questions">
        {/* Question 1: Overall Engagement */}
        <div className="survey-question" data-testid="post-video-survey">
          <span className="survey-question-label">How engaging was this video?</span>
          <div className="survey-stars" role="radiogroup" aria-label="Overall engagement rating">
            {[1, 2, 3, 4, 5].map((star) => {
              const filled = Number(surveyOverallEngagement) >= star;
              return (
                <button
                  key={star}
                  type="button"
                  className={`survey-star ${filled ? 'survey-star--filled' : ''}`}
                  onClick={() => setSurveyOverallEngagement(String(star))}
                  aria-label={`${star} star${star > 1 ? 's' : ''}`}
                  data-testid={`survey-engagement-star-${star}`}
                >
                  <svg width="48" height="48" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.27 5.82 22 7 14.14l-5-4.87 6.91-1.01L12 2z" />
                  </svg>
                </button>
              );
            })}
          </div>
          <span className="survey-star-hint">
            {Number(surveyOverallEngagement) === 1 ? 'Not engaging' :
             Number(surveyOverallEngagement) === 2 ? 'Slightly engaging' :
             Number(surveyOverallEngagement) === 3 ? 'Moderately engaging' :
             Number(surveyOverallEngagement) === 4 ? 'Very engaging' :
             Number(surveyOverallEngagement) === 5 ? 'Extremely engaging' : '\u00A0'}
          </span>
        </div>

        {/* Question 2: Content Clarity */}
        <div className="survey-question">
          <span className="survey-question-label">How clear was the content?</span>
          <div className="survey-stars" role="radiogroup" aria-label="Content clarity rating">
            {[1, 2, 3, 4, 5].map((star) => {
              const filled = Number(surveyContentClarity) >= star;
              return (
                <button
                  key={star}
                  type="button"
                  className={`survey-star ${filled ? 'survey-star--filled' : ''}`}
                  onClick={() => setSurveyContentClarity(String(star))}
                  aria-label={`${star} star${star > 1 ? 's' : ''}`}
                  data-testid={`survey-clarity-star-${star}`}
                >
                  <svg width="48" height="48" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.27 5.82 22 7 14.14l-5-4.87 6.91-1.01L12 2z" />
                  </svg>
                </button>
              );
            })}
          </div>
          <span className="survey-star-hint">
            {Number(surveyContentClarity) === 1 ? 'Very unclear' :
             Number(surveyContentClarity) === 2 ? 'Somewhat unclear' :
             Number(surveyContentClarity) === 3 ? 'Neutral' :
             Number(surveyContentClarity) === 4 ? 'Clear' :
             Number(surveyContentClarity) === 5 ? 'Very clear' : '\u00A0'}
          </span>
        </div>

        {/* Open-ended Comment Box */}
        <div className="survey-question survey-question--comment">
          <label className="survey-question-label" htmlFor="survey-comments">
            Anything else you want to share?
          </label>
          <textarea
            id="survey-comments"
            className="survey-comment-box"
            rows={5}
            value={surveyAdditionalComments}
            onChange={(event) => setSurveyAdditionalComments(event.target.value)}
            placeholder="What stood out? What could be better? Any moments that surprised you?"
            data-testid="survey-additional-comments-input"
          />
        </div>
      </div>

      <button
        className="survey-submit-btn"
        onClick={finishAndUpload}
        data-testid="finish-button"
        disabled={!canFinishSession}
      >
        Submit &amp; Finish
      </button>
      {!canFinishSession ? (
        <p className="survey-validation-hint">
          Please rate both questions to continue.
        </p>
      ) : null}
    </section>
  );
}
