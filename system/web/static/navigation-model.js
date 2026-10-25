(function (root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.NavigationModel = model;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  // Presentation only. Remembers where a reviewer was during this page session so
  // leaving for Project, Requests or Rules can return them to the same review.
  // It never selects a review the caller did not pass as eligible, and it does not
  // persist anything: review status, authority and decisions stay server records.
  const SECTIONS = Object.freeze(['overview', 'changes', 'evidence', 'audit']);
  const DEFAULT_SECTION = 'overview';

  function validId(value) {
    return typeof value === 'string' && value.length > 0;
  }

  function validSection(section) {
    return SECTIONS.includes(section) ? section : DEFAULT_SECTION;
  }

  // A review without project_id is trusted to the caller's project scope; one that
  // names another project is never eligible, even if it was passed in by mistake.
  function belongsTo(projectId, review) {
    if (!review || typeof review !== 'object' || !validId(review.id)) return false;
    return review.project_id === undefined || review.project_id === null || review.project_id === projectId;
  }

  function createSession() {
    const remembered = new Map();

    function remember(projectId, reviewId, section = DEFAULT_SECTION) {
      if (!validId(projectId) || !validId(reviewId)) return false;
      remembered.set(projectId, {reviewId, section: validSection(section)});
      return true;
    }

    // A remembered review that is filtered out or removed is skipped, not forgotten:
    // clearing a filter can bring the reviewer back to where they were.
    function restore(projectId, eligibleReviews) {
      if (!validId(projectId) || !Array.isArray(eligibleReviews)) return null;
      const eligible = eligibleReviews.filter(review => belongsTo(projectId, review));
      if (!eligible.length) return null;
      const entry = remembered.get(projectId);
      const review = entry && eligible.find(item => item.id === entry.reviewId);
      if (review) return {review, section: entry.section};
      return {review: eligible[0], section: DEFAULT_SECTION};
    }

    function clear() {
      remembered.clear();
    }

    return {remember, restore, clear};
  }

  return {SECTIONS, createSession};
});
