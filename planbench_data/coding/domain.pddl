(define (domain coding)
  (:requirements :strips :typing)
  (:types file test)
  
  (:predicates
    (file-exists ?f - file)
    (file-read ?f - file)
    (test-exists ?t - test)
    (test-passing ?t - test)
    (bug-fixed ?t - test)
  )

  ;; Read a file to understand context
  (:action read-file
    :parameters (?f - file)
    :precondition (file-exists ?f)
    :effect (file-read ?f)
  )

  ;; Edit a file to fix a bug
  ;; We model this optimistically: editing a file *might* fix the bug
  (:action edit-file
    :parameters (?f - file ?t - test)
    :precondition (and (file-exists ?f) (file-read ?f))
    :effect (bug-fixed ?t)
  )

  ;; Run a test to verify the fix
  (:action run-test
    :parameters (?t - test)
    :precondition (and (test-exists ?t) (bug-fixed ?t))
    :effect (test-passing ?t)
  )
)
