# Scale Overview
This file describes the draft scale and how the sections are organized.
The opening lines under a top heading should be treated as shared context for its children.

## Purpose
This section explains why the scale is being built.
It should be easy to retrieve without unrelated later sections.

### Target Population
This subsection defines who the scale is for.
It gives a narrow scope for later item design.

### Use Scenario
This subsection explains when the scale will be used.
It is a sibling of Target Population and should be skippable when not requested.

## Structure
This section lists the high-level design of the scale.
Its own intro should appear before its children when one child is requested.

### Domains
This subsection names the major domains.
It acts as a parent for deeper content if needed later.

### Scoring
This subsection explains how scores are summarized.
It should be returned fully if selected as the target.

# Contextual Read Cases
This top section is mainly for testing contextual reconstruction.
Its intro should appear when any child under this heading is requested.

### Early Detail
This node appears before a level-2 sibling on purpose.
It is here to test heading jumps and path-aware reconstruction.

### Later Detail
This is another sibling under the same top context.
It should not be returned when only Early Detail is requested.

## Branch Node
This section comes after level-3 nodes under the same top heading.
Its intro should be preserved when its child is selected.

### Leaf Node
This is the deepest target in this branch.
When requested, the output should include Contextual Read Cases intro, Branch Node intro, and this node.

## Export
This section explains how final results are saved.
It is unrelated to the Branch Node subtree and should be omitted unless explicitly requested.

### JSON Export
This subsection describes JSON output.
It is useful for testing another normal parent-child case.